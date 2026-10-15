from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import websockets

from database import get_async_session
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerStatus


_DEFAULT_SHELL_ROWS = 24
_DEFAULT_SHELL_COLS = 80

# 交互式 shell 原先由容器内 Go 控制面的 WebSocket /shell 提供；ravenholt 官方沙箱镜像没有该
# 控制面，无法建立 PTY 会话。这里显式失败，避免伪装成可用。
_SHELL_UNAVAILABLE_MESSAGE = (
    "sandbox container shell is unavailable: the ravenholt sandbox image does not provide the "
    "in-container control plane (/shell) that the interactive shell relied on"
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
    raise RuntimeError(_SHELL_UNAVAILABLE_MESSAGE)


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
