from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import websockets

from database import get_async_session
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerStatus
from service.sandbox.control_proxy import resolve_sandbox_control_proxy_target


_DEFAULT_SHELL_ROWS = 24
_DEFAULT_SHELL_COLS = 80
_SHELL_OPEN_TIMEOUT_SECONDS = 15

_SHELL_UNAVAILABLE_MESSAGE = (
    "sandbox container shell is unavailable: the in-container control plane is not running "
    "(missing SANDBOX_CONTROL_PROXY_TOKEN or the container is not reachable from the platform)"
)


@dataclass
class ContainerShellSession:
    websocket: Any
    closed: bool = False

    def shutdown(self) -> None:
        return None

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        await self.websocket.close()


async def resolve_shell_container(id: int) -> SandboxContainer | None:
    async with get_async_session() as session:
        container = await session.get(SandboxContainer, id)
        if container is None or container.status != SandboxContainerStatus.RUNNING:
            return None
        return container


async def open_container_shell(
    id: int,
    rows: int = _DEFAULT_SHELL_ROWS,
    cols: int = _DEFAULT_SHELL_COLS,
) -> ContainerShellSession:
    """经容器内 Go 控制面的 ``/shell`` 建立 PTY WebSocket 会话。

    控制面由容器 entrypoint 启动（supervisord），平台只做转发：容器在 macvlan 网络上时
    按容器 IP 直连，bridge 模式下按记录里的宿主端口直连（见
    ``resolve_sandbox_control_proxy_target``）。
    """
    target = await resolve_sandbox_control_proxy_target(id, require_running=True)
    if target is None:
        raise RuntimeError(_SHELL_UNAVAILABLE_MESSAGE)
    url = f"{target.ws_base_url}/shell?token={quote(target.token)}"
    try:
        websocket = await websockets.connect(
            url,
            max_size=None,
            ping_interval=20,
            open_timeout=_SHELL_OPEN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - 连接失败统一收敛成不可用
        raise RuntimeError(f"{_SHELL_UNAVAILABLE_MESSAGE} ({exc})") from exc
    session = ContainerShellSession(websocket=websocket)
    await resize_container_shell(session, rows=rows, cols=cols)
    return session


async def resize_container_shell(session: ContainerShellSession, rows: int, cols: int) -> None:
    rows = max(1, min(rows, 300))
    cols = max(1, min(cols, 500))
    await session.websocket.send(_resize_message(rows, cols))


async def read_container_shell(session: ContainerShellSession) -> bytes:
    try:
        data = await session.websocket.recv()
    except (websockets.exceptions.ConnectionClosed, OSError, ValueError, asyncio.CancelledError):
        return b""
    if isinstance(data, str):
        return data.encode()
    return data or b""


async def write_container_shell(session: ContainerShellSession, data: str) -> None:
    if not data:
        return
    await session.websocket.send(data)


def _resize_message(rows: int, cols: int) -> str:
    return f"\x00resize:{rows}:{cols}"
