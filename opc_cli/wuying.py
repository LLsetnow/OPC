"""无影灵构工作站 API 客户端。

无影灵构的工作站 API 使用 POST + JSON，请求动作通过 URL 的 ``Action``
参数指定，ApiKey 默认放在 JSON Body 中。这个模块只负责协议和请求，CLI
参数与输出由 :mod:`opc_cli.cli` 负责。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Optional

import requests


DEFAULT_ENDPOINT = "https://wuying-personal-pc.cn-hangzhou.aliyuncs.com"
DEFAULT_API_VERSION = "2025-11-11"
DEFAULT_SIGNATURE_VERSION = "1.0"
DEFAULT_API_KEY_ENV = "WUYING_API_KEY"
LEGACY_API_KEY_ENV = "LINCORE_API_KEY"
_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


class WuyingError(RuntimeError):
    """无影灵构 API 调用或参数错误。"""


def resolve_api_key(explicit_key: Optional[str] = None) -> str:
    """从显式参数或环境变量读取 ApiKey，不输出密钥内容。"""

    if explicit_key and explicit_key.strip():
        return explicit_key.strip()

    import os

    return (
        os.environ.get(DEFAULT_API_KEY_ENV, "").strip()
        or os.environ.get(LEGACY_API_KEY_ENV, "").strip()
    )


def _redact(value: Any, secret: str) -> str:
    """将异常/非 JSON 响应中的 ApiKey 脱敏。"""

    text = str(value)
    if secret:
        text = text.replace(secret, "***")
    return text


def _api_error(data: Any) -> Optional[str]:
    """识别 HTTP 200 但业务失败的常见响应格式。"""

    if not isinstance(data, dict):
        return None

    success = data.get("Success", data.get("success"))
    if success is False:
        return str(data.get("Message") or data.get("message") or "API 返回失败")

    code = data.get("Code", data.get("code"))
    if code is None:
        return None
    normalized = str(code).strip().lower()
    if normalized in {"", "0", "200", "ok", "success"}:
        return None
    return str(data.get("Message") or data.get("message") or f"API 返回错误码 {code}")


class WuyingClient:
    """无影灵构工作站 API 的轻量客户端。"""

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        api_version: str = DEFAULT_API_VERSION,
        signature_version: str = DEFAULT_SIGNATURE_VERSION,
        api_key_placement: str = "body",
        timeout: float = 30,
        session: Optional[requests.Session] = None,
    ) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise WuyingError(
                "未设置 WUYING_API_KEY。请在 .env 配置访问令牌，或通过 --api-key 传入。"
            )

        endpoint = endpoint.strip().rstrip("/")
        if not endpoint.startswith(("http://", "https://")):
            raise WuyingError("无影灵构 API endpoint 必须以 http:// 或 https:// 开头")
        if api_key_placement not in {"body", "query"}:
            raise WuyingError("--api-key-placement 只能是 body 或 query")
        if timeout <= 0:
            raise WuyingError("API 请求超时必须大于 0 秒")

        self.api_key = api_key
        self.endpoint = endpoint
        self.api_version = api_version.strip() or DEFAULT_API_VERSION
        self.signature_version = signature_version.strip() or DEFAULT_SIGNATURE_VERSION
        self.api_key_placement = api_key_placement
        self.timeout = timeout
        self.session = session or requests.Session()

    def request(self, action: str, payload: Optional[Mapping[str, Any]] = None) -> Any:
        """调用指定 Action 并返回 JSON 响应。"""

        action = action.strip()
        if not _ACTION_RE.fullmatch(action):
            raise WuyingError(f"非法 Action: {action!r}")

        params = {
            "Action": action,
            "Format": "JSON",
            "Version": self.api_version,
            "SignatureVersion": self.signature_version,
        }
        body = dict(payload or {})
        if self.api_key_placement == "body":
            body["ApiKey"] = self.api_key
        else:
            params["ApiKey"] = self.api_key

        try:
            response = self.session.post(
                self.endpoint,
                params=params,
                json=body,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise WuyingError(f"请求无影灵构 API 失败: {_redact(exc, self.api_key)}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            detail = _redact(response.text[:1000], self.api_key)
            raise WuyingError(
                f"无影灵构 API 返回非 JSON 响应（HTTP {response.status_code}）: {detail}"
            ) from exc

        if not 200 <= response.status_code < 300:
            raise WuyingError(
                f"无影灵构 API 请求失败（HTTP {response.status_code}）: "
                f"{_redact(_compact_json(data), self.api_key)}"
            )

        business_error = _api_error(data)
        if business_error:
            raise WuyingError(f"无影灵构 API 返回失败: {_redact(business_error, self.api_key)}")
        return data


def parse_json_body(body: Optional[str] = None, body_file: Optional[str] = None) -> dict[str, Any]:
    """解析通用 request 的 JSON Body，支持直接 JSON 或文件。"""

    if body and body_file:
        raise WuyingError("--body 和 --body-file 只能二选一")
    if body_file:
        try:
            text = Path(body_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise WuyingError(f"读取 Body 文件失败: {body_file}: {exc}") from exc
    else:
        text = body or "{}"

    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise WuyingError(f"Body 不是合法 JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise WuyingError("API Body 必须是 JSON 对象")
    return value


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_result(value: Any, *, compact: bool = False) -> str:
    """格式化 CLI 输出。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        indent=None if compact else 2,
    )


def create_order(
    client: WuyingClient,
    *,
    desktop_name: str,
    image_id: str,
    product_code: str,
    amount: int = 1,
    sku: str = "CUSTOM",
    root_disk_size: int = 100,
    data_disk_size: int = 40,
    internet_bandwidth: int = 40,
) -> Any:
    """创建动态工作站订单。"""

    return client.request(
        "CreateOrder",
        {
            "OperationType": "DYNAMIC_CREATE",
            "DynamicProductParams": [
                {
                    "InputActivateConfig": {
                        "DesktopName": desktop_name,
                        "ImageId": image_id,
                    },
                    "ProductCode": product_code,
                    "Amount": str(amount),
                    "ProductSkuCode": sku,
                    "DynamicAttributes": {
                        "RootDiskSize": str(root_disk_size),
                        "DataDiskSize": str(data_disk_size),
                        "InternetBandWidth": str(internet_bandwidth),
                    },
                }
            ],
        },
    )


def describe_desktops(
    client: WuyingClient,
    *,
    desktop_id: Optional[str] = None,
    display_type: str = "Linggou",
) -> Any:
    payload: dict[str, Any] = {"DisplayType": display_type}
    if desktop_id:
        payload["DesktopId"] = desktop_id
    return client.request("DescribeDesktops", payload)


def generate_scene_url(
    client: WuyingClient,
    *,
    desktop_id: str,
    product_type: str = "WuyingWorkStation",
    scene: str = "ComfyUi",
    client_type: Optional[str] = None,
) -> Any:
    payload: dict[str, Any] = {
        "WuyingServerId": desktop_id,
        "ProductType": product_type,
        "Scene": scene,
    }
    if client_type:
        payload["ClientType"] = client_type
    return client.request("GenerateWuyingServerSceneUrl", payload)


def create_desktop_image(
    client: WuyingClient,
    *,
    desktop_id: str,
    disk_type: str = "ALL",
    image_name: str,
    description: str = "",
) -> Any:
    return client.request(
        "CreateDesktopImage",
        {
            "DesktopId": desktop_id,
            "DiskType": disk_type,
            "ImageName": image_name,
            "Description": description,
        },
    )


def describe_core_package_list(
    client: WuyingClient,
    *,
    query_deduction_instances: bool = False,
    query_scenario: Optional[str] = "LinggouScenario",
) -> Any:
    payload: dict[str, Any] = {
        "QueryDeductionInstances": query_deduction_instances,
    }
    if query_scenario:
        payload["QueryScenario"] = query_scenario
    return client.request("DescribeCorePackageList", payload)


def describe_package_orders(
    client: WuyingClient,
    *,
    current_page: int = 1,
    page_size: int = 10,
    product_type_list: Optional[list[str]] = None,
) -> Any:
    payload: dict[str, Any] = {
        "CurrentPage": current_page,
        "PageSize": page_size,
    }
    if product_type_list:
        payload["ProductTypeList"] = product_type_list
    return client.request("DescribePackageOrders", payload)
