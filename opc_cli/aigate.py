"""云扉（AIGate）ComfyUI 实例管理和原生工作流提交。"""

import json
import mimetypes
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode

import requests

from .comfyui import find_nodes_by_class, generate_random_seed


AIGATE_API_BASE = "https://waas.aigate.cc/api/openapi"
_DEFAULT_REQUEST_TIMEOUT = 15
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
DEFAULT_WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflows"
# 云扉的 skuList 接口要求 areaName。此列表以当前 OpenAPI 文档为准；传入
# --area 时始终只查询用户指定的区域。
_DEFAULT_SKU_AREAS = ("华东一区", "华东二区")


class AigateError(RuntimeError):
    """可安全展示给 CLI 用户的云扉或 ComfyUI 错误。"""


def normalize_bearer_token(value: str) -> str:
    """接受纯 Token 或 ``Bearer <token>``，但绝不在错误中回显凭证。"""
    token = str(value or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if not token:
        raise AigateError("未设置云扉 Token。请配置 AIGATE_TOKEN 或传入 --token。")
    return token


def list_workflow_files(workflow_dir: Optional[str] = None) -> list[Path]:
    """返回仓库中可供 ``opc aigate --run`` 使用的 JSON 工作流文件。"""
    directory = (
        Path(workflow_dir).expanduser()
        if workflow_dir
        else DEFAULT_WORKFLOW_DIR
    )
    if not directory.is_dir():
        raise AigateError(f"工作流目录不存在: {directory}")
    return sorted(
        (path for path in directory.rglob("*.json") if path.is_file()),
        key=lambda path: str(path.relative_to(directory)),
    )


def _safe_json(response: requests.Response, service_name: str) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise AigateError(f"{service_name} 返回了无效响应") from exc
    if not isinstance(body, dict):
        raise AigateError(f"{service_name} 返回了无效响应")
    return body


def _safe_error_message(body: dict) -> str:
    """提取可展示的简短错误，不回显请求体、响应体或认证信息。"""
    error = body.get("error")
    if isinstance(error, dict):
        value = error.get("message") or error.get("type")
    else:
        value = body.get("message") or body.get("msg") or error
    message = " ".join(str(value or "").split())
    return message[:300]


def _aigate_json(
    method: str,
    path: str,
    token: str,
    payload: Optional[dict] = None,
    *,
    api_base: str = AIGATE_API_BASE,
    timeout: int = _DEFAULT_REQUEST_TIMEOUT,
) -> Any:
    """调用云扉 OpenAPI；异常消息不包含 Token 或远端原始响应。"""
    url = api_base.rstrip("/") + path
    try:
        response = requests.request(
            method,
            url,
            headers={"Authorization": "Bearer " + normalize_bearer_token(token)},
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise AigateError("云扉实例服务请求超时") from exc
    except requests.RequestException as exc:
        raise AigateError("无法连接云扉实例服务") from exc

    body = _safe_json(response, "云扉")
    if not response.ok:
        raise AigateError(f"云扉实例服务请求失败（HTTP {response.status_code}）")
    if body.get("code") != 0:
        raise AigateError("云扉实例服务拒绝了请求")
    return body.get("data")


def _comfyui_json(
    method: str,
    url: str,
    *,
    payload: Optional[dict] = None,
    files: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: int = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """调用公开的原生 ComfyUI API；该请求绝不携带云扉 Token。"""
    try:
        response = requests.request(
            method,
            url,
            json=payload,
            files=files,
            data=data,
            headers={},
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise AigateError("云扉 ComfyUI 请求超时") from exc
    except requests.RequestException as exc:
        raise AigateError("无法连接云扉 ComfyUI 服务") from exc

    body = _safe_json(response, "ComfyUI")
    if not response.ok:
        detail = _safe_error_message(body)
        suffix = f"：{detail}" if detail else ""
        raise AigateError(f"ComfyUI 请求失败（HTTP {response.status_code}）{suffix}")
    return body


def list_instances(token: str, *, api_base: str = AIGATE_API_BASE) -> list[dict]:
    """分页返回云扉控制台中的全部实例记录。"""
    page_size = 20
    current = 1
    result = []
    while True:
        data = _aigate_json(
            "POST",
            "/instance/page",
            token,
            {"current": current, "pageSize": page_size},
            api_base=api_base,
        )
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise AigateError("云扉未返回有效实例列表")
        result.extend(item for item in records if isinstance(item, dict))
        total = data.get("total") if isinstance(data, dict) else None
        try:
            total_count = int(total)
        except (TypeError, ValueError):
            raise AigateError("云扉未返回有效实例总数")
        if total_count < 0:
            raise AigateError("云扉未返回有效实例总数")
        if len(result) >= total_count or len(records) < page_size:
            return result
        current += 1


def list_skus(
    token: str, area_name: Optional[str] = None, *, api_base: str = AIGATE_API_BASE
) -> list[dict]:
    """返回当前 Token 可创建实例的 GPU SKU，可按区域筛选。"""
    selected_area = str(area_name or "").strip()
    areas = (selected_area,) if selected_area else _DEFAULT_SKU_AREAS
    result = []
    seen = set()
    for area in areas:
        data = _aigate_json(
            "GET",
            "/instance/skuList?" + urlencode({"areaName": area}),
            token,
            api_base=api_base,
        )
        if not isinstance(data, list):
            raise AigateError("云扉未返回有效 GPU SKU 列表")
        for item in data:
            if not isinstance(item, dict):
                continue
            key = (str(item.get("areaName") or area), str(item.get("skuName") or ""))
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def list_personal_images(
    token: str, *, api_base: str = AIGATE_API_BASE
) -> list[dict]:
    """分页返回当前 Token 名下的全部个人镜像。"""
    page_size = 20
    current = 1
    result = []
    while True:
        data = _aigate_json(
            "POST",
            "/image/page",
            token,
            {"current": current, "pageSize": page_size, "imageType": "3"},
            api_base=api_base,
        )
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise AigateError("云扉未返回有效个人镜像列表")
        result.extend(item for item in records if isinstance(item, dict))
        total = data.get("total") if isinstance(data, dict) else None
        try:
            total_count = int(total)
        except (TypeError, ValueError):
            raise AigateError("云扉未返回有效个人镜像总数")
        if total_count < 0:
            raise AigateError("云扉未返回有效个人镜像总数")
        if len(result) >= total_count or len(records) < page_size:
            return result
        current += 1


def list_community_images(
    token: str,
    area_name: str,
    sku_name: str,
    image_name: str = "",
    *,
    api_base: str = AIGATE_API_BASE,
) -> list[dict]:
    """分页返回指定区域和 SKU 下可用的社区镜像。"""
    area_name = str(area_name or "").strip()
    sku_name = str(sku_name or "").strip()
    if not area_name or not sku_name:
        raise AigateError("查询社区镜像时必须提供 --area 和 --sku。")
    page_size = 20
    current = 1
    result = []
    while True:
        data = _aigate_json(
            "POST",
            "/image/page",
            token,
            {
                "current": current,
                "pageSize": page_size,
                "imageType": "2",
                "areaName": area_name,
                "skuName": sku_name,
                "imageName": str(image_name or "").strip(),
                "imageVersion": "",
            },
            api_base=api_base,
        )
        records = data.get("records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise AigateError("云扉未返回有效社区镜像列表")
        result.extend(item for item in records if isinstance(item, dict))
        total = data.get("total") if isinstance(data, dict) else None
        try:
            total_count = int(total)
        except (TypeError, ValueError):
            raise AigateError("云扉未返回有效社区镜像总数")
        if total_count < 0:
            raise AigateError("云扉未返回有效社区镜像总数")
        if len(result) >= total_count or len(records) < page_size:
            return result
        current += 1


def get_instance_detail(
    token: str, instance_id: str, *, api_base: str = AIGATE_API_BASE
) -> dict:
    instance_id = str(instance_id or "").strip()
    if not instance_id:
        raise AigateError("请通过 --instance 指定云扉实例。")
    data = _aigate_json(
        "GET",
        "/instance/get?" + urlencode({"instanceId": instance_id}),
        token,
        api_base=api_base,
    )
    if not isinstance(data, dict):
        raise AigateError("云扉未返回有效实例详情")
    return data


def find_comfyui_host(detail: dict) -> str:
    """从实例详情中取得 ComfyUI 的公开域名。"""
    services = detail.get("instanceUtilList") if isinstance(detail, dict) else None
    if not isinstance(services, list):
        return ""
    for service in services:
        if not isinstance(service, dict) or service.get("name") != "ComfyUI":
            continue
        host = str(service.get("host") or "").strip()
        if host:
            return host
    return ""


def make_comfyui_base_url(host: str) -> str:
    value = str(host or "").strip()
    if not value or not _HOST_RE.fullmatch(value):
        raise AigateError("云扉实例未返回有效的 ComfyUI 服务地址")
    return "https://" + value


def instance_summary(detail: dict) -> dict:
    """形成适合 CLI 显示的实例摘要，不包含认证信息。"""
    return {
        "instance_id": str(detail.get("instanceId") or ""),
        "instance_name": str(detail.get("instanceName") or "未命名实例"),
        "status": str(detail.get("operationStatus") or ""),
        "has_comfyui": bool(find_comfyui_host(detail)),
    }


def control_instance(
    token: str, instance_id: str, action: str, *, api_base: str = AIGATE_API_BASE
) -> None:
    action = str(action or "").strip().lower()
    if action not in ("open", "close", "release"):
        raise AigateError("云扉实例操作无效")
    instance_id = str(instance_id or "").strip()
    if not instance_id:
        raise AigateError("请通过 --instance 指定云扉实例。")
    _aigate_json(
        "GET",
        "/instance/" + action + "?" + urlencode({"instanceId": instance_id}),
        token,
        api_base=api_base,
    )


def create_instance(
    token: str,
    sku: str,
    area: str,
    image_id: str,
    image_type: str,
    *,
    api_base: str = AIGATE_API_BASE,
) -> dict:
    """创建一台预设镜像实例。调用方需显式确认 --create。"""
    missing = []
    values = {
        "--sku / AIGATE_SKU_NAME": sku,
        "--area / AIGATE_AREA_NAME": area,
        "--image-id / AIGATE_IMAGE_ID": image_id,
        "--image-type / AIGATE_IMAGE_TYPE": image_type,
    }
    for name, value in values.items():
        if not str(value or "").strip():
            missing.append(name)
    if missing:
        raise AigateError("创建云扉实例缺少配置: " + "、".join(missing))

    try:
        numeric_image_id = int(str(image_id).strip())
    except ValueError as exc:
        raise AigateError("--image-id 必须是云扉镜像 ID。") from exc
    if numeric_image_id < 0 or str(image_type).strip() not in ("2", "3"):
        raise AigateError("云扉镜像配置无效，请检查 --image-id 和 --image-type。")

    data = _aigate_json(
        "POST",
        "/instance/start",
        token,
        {
            "skuName": str(sku).strip(),
            "areaName": str(area).strip(),
            "count": 1,
            "imageId": numeric_image_id,
            "imageType": str(image_type).strip(),
        },
        api_base=api_base,
    )
    if not isinstance(data, dict) or not str(data.get("instanceId") or "").strip():
        raise AigateError("云扉未返回新实例 ID")
    return data


def _select_comfyui_instance(
    token: str, instance_id: Optional[str], *, api_base: str = AIGATE_API_BASE
) -> dict:
    """选定一个明确指定的或首个带 ComfyUI 服务的实例详情。"""
    if instance_id:
        detail = get_instance_detail(token, instance_id, api_base=api_base)
        if not find_comfyui_host(detail):
            raise AigateError("指定实例未发现 ComfyUI 服务。")
        return detail

    for record in list_instances(token, api_base=api_base):
        candidate_id = str(record.get("instanceId") or "").strip()
        if not candidate_id:
            continue
        detail = get_instance_detail(token, candidate_id, api_base=api_base)
        if find_comfyui_host(detail):
            return detail
    raise AigateError("未找到包含 ComfyUI 服务的云扉实例。")


def wait_for_comfyui(
    token: str,
    instance_id: str,
    *,
    timeout: int = 300,
    poll_interval: int = 3,
    api_base: str = AIGATE_API_BASE,
    on_wait: Optional[Callable[[str], None]] = None,
) -> dict:
    """等候云扉分配实例并确认其 ComfyUI HTTP 服务可用。"""
    deadline = time.monotonic() + max(1, timeout)
    last_message = "正在等待云扉 ComfyUI 服务就绪…"
    while time.monotonic() < deadline:
        detail = get_instance_detail(token, instance_id, api_base=api_base)
        host = find_comfyui_host(detail)
        if host:
            base_url = make_comfyui_base_url(host)
            try:
                _comfyui_json("GET", base_url + "/system_stats", timeout=5)
                return {
                    "instance_id": str(detail.get("instanceId") or instance_id),
                    "instance_name": str(detail.get("instanceName") or "未命名实例"),
                    "base_url": base_url,
                }
            except AigateError:
                last_message = "ComfyUI 服务尚未就绪，继续等待…"
        else:
            status = str(detail.get("operationStatus") or "")
            last_message = "云扉正在启动实例（状态 " + (status or "未知") + "）…"
        if on_wait:
            on_wait(last_message)
        time.sleep(max(1, poll_interval))
    raise AigateError("等待云扉 ComfyUI 服务就绪超时。")


def start_comfyui(
    token: str,
    instance_id: Optional[str] = None,
    *,
    timeout: int = 300,
    poll_interval: int = 3,
    api_base: str = AIGATE_API_BASE,
    on_wait: Optional[Callable[[str], None]] = None,
) -> dict:
    """启动现有实例，并返回已就绪的 ComfyUI URL。"""
    detail = _select_comfyui_instance(token, instance_id, api_base=api_base)
    selected_id = str(detail.get("instanceId") or "").strip()
    # 云扉新建实例返回状态 "1"，此时已经在分配资源；重复调用 open
    # 会让创建流程报错。对其只轮询就绪状态，已停止的实例才发送 open。
    if str(detail.get("operationStatus") or "") not in ("1", "2"):
        control_instance(token, selected_id, "open", api_base=api_base)
    return wait_for_comfyui(
        token,
        selected_id,
        timeout=timeout,
        poll_interval=poll_interval,
        api_base=api_base,
        on_wait=on_wait,
    )


def discover_running_comfyui(
    token: str, instance_id: Optional[str] = None, *, api_base: str = AIGATE_API_BASE
) -> dict:
    """发现已运行的 ComfyUI 实例，不会启动或创建云资源。"""
    if instance_id:
        detail = _select_comfyui_instance(token, instance_id, api_base=api_base)
        if str(detail.get("operationStatus") or "") != "2":
            raise AigateError("指定云扉实例未运行，请先使用 --start。")
        return {
            "instance_id": str(detail.get("instanceId") or instance_id),
            "instance_name": str(detail.get("instanceName") or "未命名实例"),
            "base_url": make_comfyui_base_url(find_comfyui_host(detail)),
        }

    for record in list_instances(token, api_base=api_base):
        if str(record.get("operationStatus") or "") != "2":
            continue
        candidate_id = str(record.get("instanceId") or "").strip()
        if not candidate_id:
            continue
        detail = get_instance_detail(token, candidate_id, api_base=api_base)
        host = find_comfyui_host(detail)
        if host:
            return {
                "instance_id": candidate_id,
                "instance_name": str(detail.get("instanceName") or "未命名实例"),
                "base_url": make_comfyui_base_url(host),
            }
    raise AigateError("没有发现运行中的云扉 ComfyUI 实例，请先使用 --start。")


def _workflow_node(workflow: dict, node_id: str, label: str) -> dict:
    node = workflow.get(node_id)
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        raise AigateError(f"工作流中的 {label} 节点 {node_id} 缺少 inputs。")
    return inputs


def _upload_input_file(base_url: str, input_path: Path) -> str:
    """上传图片、视频等 ComfyUI input 文件，并返回远端文件名。"""
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    try:
        with input_path.open("rb") as input_file:
            body = _comfyui_json(
                "POST",
                base_url.rstrip("/") + "/upload/image",
                files={"image": (input_path.name, input_file, content_type)},
                data={"type": "input"},
                timeout=60,
            )
    except OSError as exc:
        raise AigateError(f"无法读取输入文件: {input_path}") from exc
    name = str(body.get("name") or "").strip()
    if not name:
        raise AigateError("ComfyUI 未返回上传文件名")
    return name


def _upload_image(base_url: str, image_path: Path) -> str:
    """兼容现有图片工作流调用。"""
    return _upload_input_file(base_url, image_path)


def _first_node_by_class(workflow: dict, class_type: str) -> Optional[str]:
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") == class_type:
            return str(node_id)
    return None


def _replace_with_vhs_video_combine(workflow: dict, node_id: str) -> None:
    """在提交时以 VideoHelperSuite 保存节点替代不可用的自定义视频保存节点。"""
    original = _workflow_node(workflow, node_id, "视频输出")
    images = original.get("image") or original.get("images")
    frame_rate = original.get("fps") or original.get("frame_rate")
    if images is None or frame_rate is None:
        raise AigateError("视频输出节点缺少 image 或 fps 输入，无法替换为 VHS_VideoCombine。")
    inputs = {
        "images": images,
        "frame_rate": frame_rate,
        "loop_count": 0,
        "filename_prefix": str(original.get("filename") or "video/ComfyUI"),
        "format": "video/h264-mp4",
        "pingpong": False,
        "save_output": True,
    }
    if original.get("audio") is not None:
        inputs["audio"] = original["audio"]
    workflow[node_id] = {
        "inputs": inputs,
        "class_type": "VHS_VideoCombine",
        "_meta": {"title": "VHS Video Combine (OPC fallback)"},
    }


def _prepare_workflow(
    workflow_path: str,
    base_url: str,
    image: Optional[str],
    prompt: Optional[str],
    seed: Optional[int],
    load_image_node: Optional[str],
    ksampler_node: Optional[str],
    save_image_node: Optional[str],
    prompt_node: Optional[str],
    seed_node: Optional[str],
    steps: Optional[int],
    cfg: Optional[float],
    denoise: Optional[float],
    output_prefix: Optional[str],
    video: Optional[str] = None,
    reference_image: Optional[str] = None,
    video_node: Optional[str] = None,
    reference_image_node: Optional[str] = None,
    video_output_node: Optional[str] = None,
) -> tuple[dict, str]:
    path = Path(workflow_path)
    if not path.is_file():
        raise AigateError(f"工作流文件不存在: {workflow_path}")
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AigateError(f"无法读取工作流 JSON: {workflow_path}") from exc
    if not isinstance(workflow, dict):
        raise AigateError("工作流 JSON 必须是包含节点的对象。")

    detected = find_nodes_by_class(workflow)
    image_node = load_image_node or detected["load_image"]
    sampler_node = ksampler_node or detected["ksampler"]
    output_node = save_image_node or detected["save_image"]
    text_node = prompt_node or (
        detected["prompt_nodes"][0] if detected["prompt_nodes"] else None
    )
    random_node = seed_node or sampler_node or (
        detected["seed_nodes"][0] if detected["seed_nodes"] else None
    )

    if image:
        local_image = Path(image)
        if not local_image.is_file():
            raise AigateError(f"输入图片不存在: {image}")
        if not image_node:
            raise AigateError("未找到 LoadImage 节点，请用 --load-image-node 指定。")
        _workflow_node(workflow, image_node, "LoadImage")["image"] = _upload_image(
            base_url, local_image
        )

    if reference_image:
        local_reference = Path(reference_image)
        if not local_reference.is_file():
            raise AigateError(f"参考图片不存在: {reference_image}")
        selected_reference_node = reference_image_node or image_node
        if not selected_reference_node:
            raise AigateError("未找到参考图片 LoadImage 节点，请用 --reference-image-node 指定。")
        _workflow_node(workflow, selected_reference_node, "参考图片 LoadImage")[
            "image"
        ] = _upload_input_file(base_url, local_reference)

    if video:
        local_video = Path(video)
        if not local_video.is_file():
            raise AigateError(f"输入视频不存在: {video}")
        selected_video_node = video_node or _first_node_by_class(workflow, "VHS_LoadVideo")
        if not selected_video_node:
            raise AigateError("未找到 VHS_LoadVideo 节点，请用 --video-node 指定。")
        _workflow_node(workflow, selected_video_node, "VHS_LoadVideo")["video"] = _upload_input_file(
            base_url, local_video
        )

    if video_output_node:
        _replace_with_vhs_video_combine(workflow, video_output_node)

    if seed is None:
        seed = generate_random_seed()
    if random_node:
        inputs = _workflow_node(workflow, random_node, "种子")
        if "seed" in inputs:
            inputs["seed"] = int(seed)

    if prompt:
        if not text_node:
            raise AigateError("未找到提示词节点，请用 --prompt-node 指定。")
        inputs = _workflow_node(workflow, text_node, "提示词")
        if "prompt" in inputs:
            inputs["prompt"] = prompt
        elif "text" in inputs:
            inputs["text"] = prompt
        else:
            raise AigateError(f"提示词节点 {text_node} 不包含 prompt 或 text 输入。")

    resolved_prefix = output_prefix or "ComfyUI"
    if output_node:
        output_inputs = _workflow_node(workflow, output_node, "SaveImage")
        if output_prefix:
            output_inputs["filename_prefix"] = output_prefix
        else:
            resolved_prefix = str(output_inputs.get("filename_prefix") or resolved_prefix)

    if sampler_node:
        sampler_inputs = _workflow_node(workflow, sampler_node, "KSampler")
        if steps is not None and "steps" in sampler_inputs:
            sampler_inputs["steps"] = steps
        if cfg is not None and "cfg" in sampler_inputs:
            sampler_inputs["cfg"] = cfg
        if denoise is not None and "denoise" in sampler_inputs:
            sampler_inputs["denoise"] = denoise

    return workflow, resolved_prefix


def _wait_for_history(base_url: str, prompt_id: str, timeout: int) -> dict:
    deadline = time.monotonic() + max(1, timeout)
    while time.monotonic() < deadline:
        history = _comfyui_json(
            "GET", base_url.rstrip("/") + "/history/" + prompt_id, timeout=10
        )
        task = history.get(prompt_id)
        status = task.get("status") if isinstance(task, dict) else None
        status_name = str(status.get("status_str") or "") if isinstance(status, dict) else ""
        if status_name.lower() in ("error", "failed"):
            raise AigateError("ComfyUI 工作流执行失败。")
        outputs = task.get("outputs") if isinstance(task, dict) else None
        if isinstance(outputs, dict) and outputs:
            return task
        time.sleep(2)
    raise AigateError(f"等待 ComfyUI 工作流超时（prompt_id: {prompt_id}）。")


def _output_files(history: dict) -> list[dict]:
    files = []
    for node_output in history.get("outputs", {}).values():
        if not isinstance(node_output, dict):
            continue
        for output_type in ("images", "gifs", "videos", "files"):
            for output_file in node_output.get(output_type, []):
                if isinstance(output_file, dict) and str(output_file.get("filename") or "").strip():
                    files.append(output_file)
    return files


def _unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / Path(filename).name
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for index in range(1, 10_000):
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise AigateError("输出目录中存在过多同名文件。")


def _download_output(base_url: str, output_file: dict, destination: Path) -> Path:
    params = {
        "filename": str(output_file.get("filename") or ""),
        "subfolder": str(output_file.get("subfolder") or ""),
        "type": str(output_file.get("type") or "output"),
    }
    try:
        response = requests.get(
            base_url.rstrip("/") + "/view?" + urlencode(params),
            headers={},
            timeout=60,
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise AigateError("下载 ComfyUI 输出超时") from exc
    except requests.RequestException as exc:
        raise AigateError("下载 ComfyUI 输出失败") from exc
    if not response.ok:
        raise AigateError(f"下载 ComfyUI 输出失败（HTTP {response.status_code}）")
    if len(response.content) > 100 * 1024 * 1024:
        raise AigateError("ComfyUI 输出文件超过 100MB，已拒绝保存。")
    target = _unique_path(destination, params["filename"])
    target.write_bytes(response.content)
    return target


def submit_workflow(
    workflow_path: str,
    base_url: str,
    *,
    image: Optional[str] = None,
    prompt: Optional[str] = None,
    seed: Optional[int] = None,
    output_dir: str = ".",
    timeout: int = 300,
    load_image_node: Optional[str] = None,
    ksampler_node: Optional[str] = None,
    save_image_node: Optional[str] = None,
    prompt_node: Optional[str] = None,
    seed_node: Optional[str] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    denoise: Optional[float] = None,
    output_prefix: Optional[str] = None,
    video: Optional[str] = None,
    reference_image: Optional[str] = None,
    video_node: Optional[str] = None,
    reference_image_node: Optional[str] = None,
    video_output_node: Optional[str] = None,
) -> list[str]:
    """上传输入、执行工作流并把云端输出下载到本地。"""
    workflow, _ = _prepare_workflow(
        workflow_path,
        base_url,
        image,
        prompt,
        seed,
        load_image_node,
        ksampler_node,
        save_image_node,
        prompt_node,
        seed_node,
        steps,
        cfg,
        denoise,
        output_prefix,
        video,
        reference_image,
        video_node,
        reference_image_node,
        video_output_node,
    )
    submitted = _comfyui_json(
        "POST",
        base_url.rstrip("/") + "/prompt",
        payload={"prompt": workflow, "client_id": "opc_aigate_" + uuid.uuid4().hex},
        timeout=30,
    )
    prompt_id = str(submitted.get("prompt_id") or "").strip()
    if not prompt_id:
        raise AigateError("ComfyUI 未返回 prompt_id。")

    history = _wait_for_history(base_url, prompt_id, timeout)
    output_files = _output_files(history)
    if not output_files:
        raise AigateError(f"工作流完成但未返回输出文件（prompt_id: {prompt_id}）。")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    return [str(_download_output(base_url, item, destination)) for item in output_files]
