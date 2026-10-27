"""noVNC 入口的反向代理（HTTP 静态资源 + WebSocket）。

noVNC 由容器内 supervisord 托管（Xvfb + x11vnc + websockify），监听容器回环
``127.0.0.1:8080``；容器内 Go 控制面把 ``/novnc/*`` 反代到该 web 根、把 ``/websockify``
透传到 VNC 通道。平台只对接控制面：容器在 macvlan 网络上时按容器 IP 直连，
bridge 模式下按记录里的宿主端口直连（见 ``resolve_sandbox_control_proxy_target``）。

前端页面完全用相对路径推导资源与 WebSocket 地址，因此平台路径前缀不需要改写响应体；
浏览器画布的 WebSocket 由 ``/{id}/novnc-ws`` 路由另行桥接到控制面的 ``/websockify``。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import websockets

from logger import get_logger
from service.sandbox.control_proxy import resolve_sandbox_control_proxy_target


logger = get_logger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_WS_OPEN_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class NoVNCTarget:
    http_base: str
    ws_base: str
    token: str


async def resolve_novnc_target(container_id: int) -> NoVNCTarget | None:
    target = await resolve_sandbox_control_proxy_target(container_id, require_running=True)
    if target is None:
        return None
    return NoVNCTarget(http_base=target.base_url, ws_base=target.ws_base_url, token=target.token)


async def proxy_novnc_http(target: NoVNCTarget, path: str, query: str = "") -> httpx.Response | None:
    suffix = f"/{path.lstrip('/')}" if path else "/"
    url = f"{target.http_base}/novnc{suffix}{f'?{query}' if query else ''}"
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=False) as client:
            return await client.get(url, headers={"X-Sandbox-Token": target.token})
    except httpx.HTTPError:
        logger.debug("novnc http proxy failed url=%s", url, exc_info=True)
        return None


async def proxy_novnc_websocket(
    target: NoVNCTarget,
    receive_from_client,
    send_to_client,
    client_connected,
    subprotocols: list[str] | None = None,
) -> None:
    url = f"{target.ws_base}/websockify?token={quote(target.token)}"
    try:
        upstream = await websockets.connect(
            url,
            max_size=None,
            ping_interval=20,
            open_timeout=_WS_OPEN_TIMEOUT_SECONDS,
            subprotocols=subprotocols or None,
        )
    except Exception:  # noqa: BLE001 - 连不上控制面就结束会话
        logger.debug("novnc websocket connect failed url=%s", url, exc_info=True)
        return

    async def client_to_upstream() -> None:
        while True:
            data = await receive_from_client()
            if data is None:
                return
            await upstream.send(data)

    async def upstream_to_client() -> None:
        async for data in upstream:
            await send_to_client(data)

    tasks = [
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await upstream.close()
