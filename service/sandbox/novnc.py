from dataclasses import dataclass

import httpx
from logger import get_logger
from service.sandbox.control_proxy import SandboxControlProxyTarget


logger = get_logger(__name__)

# noVNC 原先由容器内 Go 控制面提供（HTTP /novnc、WebSocket /websockify）。ravenholt 官方沙箱
# 镜像没有该控制面，因此永远无法建立 noVNC 目标/代理。这里显式失败，避免伪装成可用。
_NOVNC_UNAVAILABLE_MESSAGE = (
    "noVNC is unavailable: the ravenholt sandbox image does not provide the in-container control "
    "plane (/novnc, /websockify) that the remote desktop proxy relied on"
)


@dataclass(frozen=True)
class NoVNCTarget:
    control_proxy: SandboxControlProxyTarget


async def resolve_novnc_target(container_id: int) -> NoVNCTarget | None:
    # ravenholt 镜像不暴露 noVNC/websockify 端点，始终没有可用目标。
    return None


async def proxy_novnc_http(target: NoVNCTarget, path: str) -> httpx.Response | None:
    raise RuntimeError(_NOVNC_UNAVAILABLE_MESSAGE)


async def proxy_novnc_websocket(
    target: NoVNCTarget,
    receive_from_client,
    send_to_client,
    client_connected,
    subprotocols: list[str] | None = None,
) -> None:
    raise RuntimeError(_NOVNC_UNAVAILABLE_MESSAGE)
