"""云扉（AIGate）ComfyUI 实例管理和原生工作流提交。"""

import json
import mimetypes
import os
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
# 云扉把服务地址放在 instanceUtilList[].host，可能带端口，也可能带查询串
# （JupyterLab 那条就是 "<id>.region1.waas.aigate.cc?token=..."）。
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+(:\d{1,5})?$")
DEFAULT_WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflows"
# 云扉的 skuList 接口要求 areaName。此列表以当前 OpenAPI 文档为准；传入
# --area 时始终只查询用户指定的区域。
_DEFAULT_SKU_AREAS = ("华东一区", "华东二区")

# 云扉实例前面是 APISIX 网关。实例进入非运行状态后网关会撤销路由并对所有
# 路径返回 404，但 OpenAPI 依旧回填旧的 host —— 所以 host 存在不代表可连。
INSTANCE_STATUS_PENDING = "1"
INSTANCE_STATUS_RUNNING = "2"
# 已观测到的 operationStatus 取值；未知取值一律按“不可用”处理并原样展示。
_INSTANCE_STATUS_LABELS = {
    "1": "创建中",
    "2": "运行中",
    "3": "已停止",
    "4": "已释放",
    "22": "停止中/网关不可用",
}

# 幂等请求（GET 以及只读的分页 POST）失败时的重试策略。
_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = (1.0, 2.5, 5.0)
_RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
# 工作流轮询期间容忍瞬时网络故障的时长：GPU 任务已经在跑，不能因为一次
# 网关抖动就丢掉结果。
_POLL_FAILURE_GRACE_SECONDS = 180
DEFAULT_MAX_DOWNLOAD_MB = 512


class AigateError(RuntimeError):
    """可安全展示给 CLI 用户的云扉或 ComfyUI 错误。"""


# ── 网络层：会话复用、代理开关、错误分类 ──────────────────────────

_SESSIONS: dict[bool, requests.Session] = {}
_TRUST_ENV = os.environ.get("AIGATE_NO_PROXY", "").strip().lower() not in (
    "1",
    "true",
    "yes",
    "on",
)


def configure_network(*, no_proxy: Optional[bool] = None) -> None:
    """设置是否绕过 shell 的 HTTP(S)_PROXY / ALL_PROXY。

    云扉的实例网关在境内，经代理出境常见连接重置；``--no-proxy`` 让 requests
    忽略环境里的代理变量。
    """
    global _TRUST_ENV
    if no_proxy is not None:
        _TRUST_ENV = not no_proxy


def _session() -> requests.Session:
    """复用连接：一次工作流轮询可能有上千次请求，不能每次重建 TLS。"""
    session = _SESSIONS.get(_TRUST_ENV)
    if session is None:
        session = requests.Session()
        session.trust_env = _TRUST_ENV
        _SESSIONS[_TRUST_ENV] = session
    return session


def _classify_request_error(exc: Exception) -> str:
    """把 requests 异常翻译成可操作的短提示，绝不回显 URL 或凭证。"""
    if isinstance(exc, requests.exceptions.ProxyError):
        return "代理连接失败（检测到 HTTP(S)_PROXY / ALL_PROXY，可加 --no-proxy 绕过）"
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS 握手失败"
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "建立连接超时"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "等待响应超时"
    if isinstance(exc, requests.Timeout):
        return "请求超时"
    if isinstance(exc, requests.exceptions.TooManyRedirects):
        return "重定向次数过多"
    if isinstance(exc, requests.exceptions.ChunkedEncodingError):
        return "响应传输中断"
    if isinstance(exc, requests.ConnectionError):
        text = str(exc).lower()
        if "reset by peer" in text or "connectionreseterror" in text:
            return "连接被对端重置"
        if "name or service not known" in text or "nodename nor servname" in text or "failed to resolve" in text:
            return "DNS 解析失败"
        if "connection refused" in text:
            return "连接被拒绝"
        if "broken pipe" in text:
            return "连接在发送过程中断开"
        return "无法建立连接"
    return type(exc).__name__


def _try_json(response: requests.Response) -> dict:
    """尽力解析响应体；网关的 HTML 错误页返回空字典而不是抛异常。"""
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _safe_json(response: requests.Response, service_name: str) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        content_type = str(response.headers.get("Content-Type") or "未知").split(";")[0]
        raise AigateError(
            f"{service_name} 返回了非 JSON 响应（HTTP {response.status_code}，"
            f"Content-Type {content_type}）"
        ) from exc
    if not isinstance(body, dict):
        raise AigateError(f"{service_name} 返回了无效响应（HTTP {response.status_code}）")
    return body


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


def _safe_error_message(body: dict) -> str:
    """提取可展示的简短错误，不回显请求体、响应体或认证信息。"""
    error = body.get("error")
    if isinstance(error, dict):
        value = error.get("message") or error.get("type")
    else:
        # error_msg 是云扉 APISIX 网关的字段，例如 "404 Route Not Found"。
        value = body.get("message") or body.get("msg") or body.get("error_msg") or error
    message = " ".join(str(value or "").split())
    return message[:300]


def _send(
    method: str,
    url: str,
    *,
    service_name: str,
    headers: Optional[dict] = None,
    payload: Optional[dict] = None,
    files: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: Any = _DEFAULT_REQUEST_TIMEOUT,
    stream: bool = False,
    retry: bool = False,
) -> requests.Response:
    """发送一次请求；``retry=True`` 时对瞬时故障做指数退避重试。

    只有幂等调用才允许重试 —— 提交工作流这类会产生副作用的请求必须传
    ``retry=False``，否则一次超时可能变成两次 GPU 任务。
    """
    attempts = _MAX_ATTEMPTS if retry else 1
    last_reason = ""
    for attempt in range(attempts):
        try:
            response = _session().request(
                method,
                url,
                headers=headers or {},
                json=payload,
                files=files,
                data=data,
                timeout=timeout,
                stream=stream,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            last_reason = _classify_request_error(exc)
            if attempt + 1 >= attempts:
                raise AigateError(f"{service_name} 连接失败：{last_reason}") from exc
        else:
            if response.status_code in _RETRY_STATUS and attempt + 1 < attempts:
                last_reason = f"HTTP {response.status_code}"
                response.close()
            else:
                return response
        time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
    raise AigateError(f"{service_name} 连接失败：{last_reason}")


def _check_status(response: requests.Response, service_name: str) -> None:
    """先看 HTTP 状态再解析响应体，避免网关的 HTML 错误页掩盖真实状态码。"""
    if response.is_redirect or response.is_permanent_redirect:
        raise AigateError(
            f"{service_name} 返回了重定向（HTTP {response.status_code}），"
            "通常表示网关未就绪或需要重新登录"
        )
    if response.ok:
        return
    detail = _safe_error_message(_try_json(response))
    suffix = f"：{detail}" if detail else ""
    raise AigateError(f"{service_name} 请求失败（HTTP {response.status_code}）{suffix}")


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
    response = _send(
        method,
        api_base.rstrip("/") + path,
        service_name="云扉实例服务",
        headers={"Authorization": "Bearer " + normalize_bearer_token(token)},
        payload=payload,
        timeout=timeout,
        retry=True,
    )
    _check_status(response, "云扉实例服务")
    body = _safe_json(response, "云扉")
    if body.get("code") != 0:
        detail = _safe_error_message(body)
        suffix = f"：{detail}" if detail else f"（code {body.get('code')}）"
        raise AigateError(f"云扉实例服务拒绝了请求{suffix}")
    return body.get("data")


def _comfyui_json(
    method: str,
    url: str,
    *,
    payload: Optional[dict] = None,
    files: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: Any = _DEFAULT_REQUEST_TIMEOUT,
    retry: bool = False,
) -> dict:
    """调用公开的原生 ComfyUI API；该请求绝不携带云扉 Token。"""
    response = _send(
        method,
        url,
        service_name="云扉 ComfyUI",
        payload=payload,
        files=files,
        data=data,
        timeout=timeout,
        retry=retry,
    )
    _check_status(response, "云扉 ComfyUI")
    return _safe_json(response, "ComfyUI")


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


def instance_status(detail: dict) -> str:
    """返回归一化后的 operationStatus 字符串。"""
    if not isinstance(detail, dict):
        return ""
    return str(detail.get("operationStatus") or "").strip()


def describe_instance_status(status: str) -> str:
    """把 operationStatus 变成人能读的说明；未知取值原样展示。"""
    value = str(status or "").strip()
    if not value:
        return "未知"
    label = _INSTANCE_STATUS_LABELS.get(value)
    return f"{label}({value})" if label else f"未知状态({value})"


def is_instance_running(detail: dict) -> bool:
    return instance_status(detail) == INSTANCE_STATUS_RUNNING


def find_comfyui_host(detail: dict) -> str:
    """从实例详情中取得 ComfyUI 的公开域名。

    注意：实例停机后云扉仍会回填这个 host，所以它只说明“曾经分配过服务”，
    不代表现在能连上；调用方必须另外检查 operationStatus 并探活。
    """
    services = detail.get("instanceUtilList") if isinstance(detail, dict) else None
    if not isinstance(services, list):
        return ""
    for service in services:
        if not isinstance(service, dict):
            continue
        if str(service.get("name") or "").strip().lower() != "comfyui":
            continue
        host = str(service.get("host") or "").strip()
        if host:
            return host
    return ""


def make_comfyui_base_url(host: str) -> str:
    value = str(host or "").strip()
    # 云扉会把查询串塞进 host（JupyterLab 就带 ?token=...）；ComfyUI 不需要它。
    value = value.split("?", 1)[0].split("#", 1)[0].strip().rstrip("/")
    if value.lower().startswith("https://"):
        value = value[8:]
    elif value.lower().startswith("http://"):
        value = value[7:]
    if not value or not _HOST_RE.fullmatch(value):
        raise AigateError("云扉实例未返回有效的 ComfyUI 服务地址")
    return "https://" + value


def instance_summary(detail: dict) -> dict:
    """形成适合 CLI 显示的实例摘要，不包含认证信息。"""
    status = instance_status(detail)
    return {
        "instance_id": str(detail.get("instanceId") or ""),
        "instance_name": str(detail.get("instanceName") or "未命名实例"),
        "status": status,
        "status_label": describe_instance_status(status),
        "running": status == INSTANCE_STATUS_RUNNING,
        "has_comfyui": bool(find_comfyui_host(detail)),
    }


def probe_comfyui(base_url: str, *, timeout: int = 10) -> str:
    """探活 ComfyUI；可用返回 ""，否则返回可展示的失败原因。"""
    try:
        _comfyui_json("GET", base_url.rstrip("/") + "/system_stats", timeout=timeout)
    except AigateError as exc:
        return str(exc)
    return ""


def ensure_comfyui_reachable(base_url: str, *, timeout: int = 10) -> None:
    """提交前探活，把“上传到一半才失败”提前成一条明确的错误。"""
    reason = probe_comfyui(base_url, timeout=timeout)
    if reason:
        raise AigateError(
            f"云扉 ComfyUI 当前不可访问（{reason}）。"
            "实例可能已停止或网关已撤销路由，请用 opc aigate --status 确认后重新 --start。"
        )


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
            raise AigateError(
                "指定实例未发现 ComfyUI 服务（当前状态 "
                f"{describe_instance_status(instance_status(detail))}）。"
                "刚创建的实例需要等云扉分配服务端口。"
            )
        return detail

    # 优先挑运行中的实例：停机实例同样会带着 host 返回，选中它必然连不上。
    fallback = None
    for record in list_instances(token, api_base=api_base):
        candidate_id = str(record.get("instanceId") or "").strip()
        if not candidate_id:
            continue
        detail = get_instance_detail(token, candidate_id, api_base=api_base)
        if not find_comfyui_host(detail):
            continue
        if is_instance_running(detail):
            return detail
        if fallback is None:
            fallback = detail
    if fallback is not None:
        return fallback
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
    last_status = ""
    last_probe_error = ""
    while True:
        detail = get_instance_detail(token, instance_id, api_base=api_base)
        status = instance_status(detail)
        last_status = describe_instance_status(status)
        host = find_comfyui_host(detail)
        if not host:
            message = f"云扉正在分配实例服务（状态 {last_status}）…"
        elif status != INSTANCE_STATUS_RUNNING:
            # host 已经回填但实例没跑起来，探活只会撞上 404，不必浪费一次请求。
            message = f"实例尚未进入运行中（状态 {last_status}）…"
        else:
            base_url = make_comfyui_base_url(host)
            last_probe_error = probe_comfyui(base_url, timeout=8)
            if not last_probe_error:
                return {
                    "instance_id": str(detail.get("instanceId") or instance_id),
                    "instance_name": str(detail.get("instanceName") or "未命名实例"),
                    "base_url": base_url,
                }
            message = f"实例已运行，ComfyUI 尚未响应（{last_probe_error}）…"
        if on_wait:
            on_wait(message)
        if time.monotonic() + max(1, poll_interval) >= deadline:
            break
        time.sleep(max(1, poll_interval))

    detail_suffix = f"；最后一次探活：{last_probe_error}" if last_probe_error else ""
    raise AigateError(
        f"等待云扉 ComfyUI 服务就绪超时（{timeout}s）。最后状态：{last_status or '未知'}"
        + detail_suffix
    )


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
    if instance_status(detail) not in (INSTANCE_STATUS_PENDING, INSTANCE_STATUS_RUNNING):
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
        if not is_instance_running(detail):
            raise AigateError(
                "指定云扉实例当前状态为 "
                f"{describe_instance_status(instance_status(detail))}，不是运行中；"
                "请先使用 --start。"
            )
        return {
            "instance_id": str(detail.get("instanceId") or instance_id),
            "instance_name": str(detail.get("instanceName") or "未命名实例"),
            "base_url": make_comfyui_base_url(find_comfyui_host(detail)),
        }

    seen_statuses = []
    for record in list_instances(token, api_base=api_base):
        candidate_id = str(record.get("instanceId") or "").strip()
        if not candidate_id:
            continue
        if not is_instance_running(record):
            seen_statuses.append(describe_instance_status(instance_status(record)))
            continue
        detail = get_instance_detail(token, candidate_id, api_base=api_base)
        host = find_comfyui_host(detail)
        if host:
            return {
                "instance_id": candidate_id,
                "instance_name": str(detail.get("instanceName") or "未命名实例"),
                "base_url": make_comfyui_base_url(host),
            }
    suffix = f"（现有实例状态：{'、'.join(seen_statuses)}）" if seen_statuses else ""
    raise AigateError(f"没有发现运行中的云扉 ComfyUI 实例{suffix}，请先使用 --start。")


def _workflow_node(workflow: dict, node_id: str, label: str) -> dict:
    node = workflow.get(node_id)
    inputs = node.get("inputs") if isinstance(node, dict) else None
    if not isinstance(inputs, dict):
        raise AigateError(f"工作流中的 {label} 节点 {node_id} 缺少 inputs。")
    return inputs


def _upload_timeout(size_bytes: int) -> tuple[int, int]:
    """按文件大小推导 (连接, 读取) 超时。

    原来固定 60 秒，实测云扉上行约 4 MB/s，超过 ~240MB 的输入必然超时。
    这里按 1 MB/s 的保守下限给预算，最少 120 秒。
    """
    return (15, max(120, int(size_bytes / (1024 * 1024)) + 120))


def _upload_input_file(
    base_url: str,
    input_path: Path,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """上传图片、视频等 ComfyUI input 文件，并返回远端文件名。

    重名时 ComfyUI 会自己改名并在响应里回传，所以重试是安全的。
    """
    content_type = mimetypes.guess_type(input_path.name)[0] or "application/octet-stream"
    try:
        size_bytes = input_path.stat().st_size
    except OSError as exc:
        raise AigateError(f"无法读取输入文件: {input_path}") from exc
    if on_progress:
        on_progress(f"上传 {input_path.name}（{size_bytes / 1048576:.1f} MB）…")

    last_error: Optional[AigateError] = None
    for attempt in range(3):
        try:
            with input_path.open("rb") as input_file:
                body = _comfyui_json(
                    "POST",
                    base_url.rstrip("/") + "/upload/image",
                    files={"image": (input_path.name, input_file, content_type)},
                    data={"type": "input"},
                    timeout=_upload_timeout(size_bytes),
                )
        except OSError as exc:
            raise AigateError(f"无法读取输入文件: {input_path}") from exc
        except AigateError as exc:
            last_error = exc
            if attempt == 2:
                break
            if on_progress:
                on_progress(f"上传失败（{exc}），重试第 {attempt + 1} 次…")
            time.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])
            continue
        name = str(body.get("name") or "").strip()
        if not name:
            raise AigateError("ComfyUI 未返回上传文件名")
        return name
    raise AigateError(f"上传 {input_path.name} 失败：{last_error}")


def _upload_image(
    base_url: str,
    image_path: Path,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
) -> str:
    """兼容现有图片工作流调用。"""
    return _upload_input_file(base_url, image_path, on_progress=on_progress)


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
    audio: Optional[str] = None,
    audio_node: Optional[str] = None,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
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
            base_url, local_image, on_progress=on_progress
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
        ] = _upload_input_file(base_url, local_reference, on_progress=on_progress)

    if video:
        local_video = Path(video)
        if not local_video.is_file():
            raise AigateError(f"输入视频不存在: {video}")
        selected_video_node = (
            video_node
            or _first_node_by_class(workflow, "VHS_LoadVideo")
            or _first_node_by_class(workflow, "LoadVideo")
        )
        if not selected_video_node:
            raise AigateError("未找到视频加载节点（VHS_LoadVideo / LoadVideo），请用 --video-node 指定。")
        video_inputs = _workflow_node(workflow, selected_video_node, "视频加载")
        uploaded_video = _upload_input_file(
            base_url, local_video, on_progress=on_progress
        )
        # VHS_LoadVideo 使用 "video" 输入键；原生 ComfyUI LoadVideo 使用 "file"。
        if "file" in video_inputs and "video" not in video_inputs:
            video_inputs["file"] = uploaded_video
        else:
            video_inputs["video"] = uploaded_video

    if audio:
        local_audio = Path(audio)
        if not local_audio.is_file():
            raise AigateError(f"输入音频不存在: {audio}")
        selected_audio_node = audio_node or _first_node_by_class(workflow, "LoadAudio")
        if not selected_audio_node:
            raise AigateError("未找到音频加载节点（LoadAudio），请用 --audio-node 指定。")
        _workflow_node(workflow, selected_audio_node, "音频加载")[
            "audio"
        ] = _upload_input_file(base_url, local_audio, on_progress=on_progress)

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


def _execution_error_detail(status: dict) -> str:
    """从 history 的 status.messages 里提取 ComfyUI 的真实报错。"""
    messages = status.get("messages") if isinstance(status, dict) else None
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, list) or len(message) < 2:
            continue
        if str(message[0]) != "execution_error" or not isinstance(message[1], dict):
            continue
        payload = message[1]
        parts = [
            str(payload.get(key) or "").strip()
            for key in ("node_type", "exception_type", "exception_message")
        ]
        detail = " / ".join(part for part in parts if part)
        if detail:
            return " ".join(detail.split())[:300]
    return ""


def _queue_position(base_url: str, prompt_id: str) -> str:
    """描述任务在 ComfyUI 队列中的位置；查询失败返回空串（纯诊断用途）。"""
    try:
        queue = _comfyui_json("GET", base_url.rstrip("/") + "/queue", timeout=10)
    except AigateError:
        return ""

    def ids(key: str) -> list[str]:
        entries = queue.get(key)
        if not isinstance(entries, list):
            return []
        return [
            str(entry[1])
            for entry in entries
            if isinstance(entry, (list, tuple)) and len(entry) > 1
        ]

    if prompt_id in ids("queue_running"):
        return "正在执行"
    pending = ids("queue_pending")
    if prompt_id in pending:
        ahead = pending.index(prompt_id) + len(ids("queue_running"))
        return f"排队中，前面还有 {ahead} 个任务"
    return ""


def _wait_for_history(
    base_url: str,
    prompt_id: str,
    timeout: int,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
) -> dict:
    """轮询任务结果，并容忍轮询期间的瞬时网络故障。

    GPU 任务此刻已经在跑，一次网关抖动不能让整轮工作白费 —— 只有在故障
    持续超过 ``_POLL_FAILURE_GRACE_SECONDS`` 后才放弃。
    """
    deadline = time.monotonic() + max(1, timeout)
    first_failure_at: Optional[float] = None
    last_failure = ""
    last_queue_report = time.monotonic()
    last_queue_state = ""
    while time.monotonic() < deadline:
        try:
            history = _comfyui_json(
                "GET", base_url.rstrip("/") + "/history/" + prompt_id, timeout=20
            )
        except AigateError as exc:
            now = time.monotonic()
            if first_failure_at is None:
                first_failure_at = now
            last_failure = str(exc)
            elapsed = now - first_failure_at
            if elapsed >= _POLL_FAILURE_GRACE_SECONDS:
                raise AigateError(
                    f"轮询 ComfyUI 结果连续失败 {int(elapsed)}s：{last_failure}"
                    f"（prompt_id: {prompt_id}，任务可能仍在云端运行）"
                ) from exc
            if on_progress:
                on_progress(f"轮询失败（{last_failure}），{int(elapsed)}s 内继续重试…")
            time.sleep(5)
            continue

        first_failure_at = None
        task = history.get(prompt_id)
        if isinstance(task, dict):
            status = task.get("status") if isinstance(task.get("status"), dict) else {}
            status_name = str(status.get("status_str") or "").lower()
            outputs = task.get("outputs")
            has_outputs = isinstance(outputs, dict) and bool(outputs)
            if status_name in ("error", "failed"):
                detail = _execution_error_detail(status)
                suffix = f"：{detail}" if detail else "。"
                raise AigateError(f"ComfyUI 工作流执行失败{suffix}")
            if status.get("completed") is True:
                if has_outputs:
                    return task
                raise AigateError(
                    f"ComfyUI 报告任务完成但没有产生任何输出（prompt_id: {prompt_id}）。"
                    "通常是工作流里没有保存节点，或保存节点未接上。"
                )
            # 旧版 ComfyUI 的 history 条目不带 completed，退回“有输出即完成”。
            if status.get("completed") is None and has_outputs:
                return task

        # 任务还没进 history：低频查一次队列，把“在排队”和“卡住了”区分开。
        now = time.monotonic()
        if now - last_queue_report >= 15:
            last_queue_report = now
            state = _queue_position(base_url, prompt_id)
            if state and state != last_queue_state:
                last_queue_state = state
                if on_progress:
                    on_progress(state + "…")
        time.sleep(2)

    queue_suffix = f"，最后队列状态：{last_queue_state}" if last_queue_state else ""
    raise AigateError(
        f"等待 ComfyUI 工作流超时（{timeout}s，prompt_id: {prompt_id}{queue_suffix}）。"
        "可以用 -t/--timeout 加大等待时间。"
    )


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


def _download_output(
    base_url: str,
    output_file: dict,
    destination: Path,
    *,
    max_download_mb: int = DEFAULT_MAX_DOWNLOAD_MB,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Path:
    """流式下载单个输出文件；超限在写盘前就拒绝，不整份读进内存。"""
    params = {
        "filename": str(output_file.get("filename") or ""),
        "subfolder": str(output_file.get("subfolder") or ""),
        "type": str(output_file.get("type") or "output"),
    }
    limit_bytes = max(1, max_download_mb) * 1024 * 1024
    response = _send(
        "GET",
        base_url.rstrip("/") + "/view?" + urlencode(params),
        service_name="下载 ComfyUI 输出",
        timeout=(15, 120),
        stream=True,
        retry=True,
    )
    with response:
        _check_status(response, "下载 ComfyUI 输出")
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > limit_bytes:
            raise AigateError(
                f"ComfyUI 输出 {params['filename']} 为 {int(declared) / 1048576:.1f} MB，"
                f"超过上限 {max_download_mb} MB；可用 --max-download-mb 调高。"
            )
        if on_progress:
            size_hint = f"（{int(declared) / 1048576:.1f} MB）" if declared and declared.isdigit() else ""
            on_progress(f"下载 {params['filename']}{size_hint}…")

        target = _unique_path(destination, params["filename"])
        written = 0
        try:
            with target.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > limit_bytes:
                        raise AigateError(
                            f"ComfyUI 输出 {params['filename']} 超过上限 "
                            f"{max_download_mb} MB；可用 --max-download-mb 调高。"
                        )
                    output.write(chunk)
        except requests.RequestException as exc:
            target.unlink(missing_ok=True)
            raise AigateError(
                f"下载 ComfyUI 输出中断：{_classify_request_error(exc)}"
            ) from exc
        except BaseException:
            target.unlink(missing_ok=True)
            raise
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
    audio: Optional[str] = None,
    audio_node: Optional[str] = None,
    max_download_mb: int = DEFAULT_MAX_DOWNLOAD_MB,
    on_progress: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """上传输入、执行工作流并把云端输出下载到本地。"""
    # 先探活再上传：实例停机后云扉仍会返回旧 host，直接开传会在几百 MB
    # 之后才失败，而且报错看不出是实例问题还是网络问题。
    ensure_comfyui_reachable(base_url)

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
        audio,
        audio_node,
        on_progress=on_progress,
    )
    # 提交不可重试：一次超时重发可能变成两个 GPU 任务。
    submitted = _comfyui_json(
        "POST",
        base_url.rstrip("/") + "/prompt",
        payload={"prompt": workflow, "client_id": "opc_aigate_" + uuid.uuid4().hex},
        timeout=(15, 60),
    )
    prompt_id = str(submitted.get("prompt_id") or "").strip()
    if not prompt_id:
        raise AigateError("ComfyUI 未返回 prompt_id。")
    if on_progress:
        on_progress(f"已提交，prompt_id: {prompt_id}")

    history = _wait_for_history(base_url, prompt_id, timeout, on_progress=on_progress)
    output_files = _output_files(history)
    if not output_files:
        raise AigateError(f"工作流完成但未返回输出文件（prompt_id: {prompt_id}）。")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    return [
        str(
            _download_output(
                base_url,
                item,
                destination,
                max_download_mb=max_download_mb,
                on_progress=on_progress,
            )
        )
        for item in output_files
    ]
