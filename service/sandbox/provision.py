"""把 strix 运行时自建的沙箱容器回写成平台记录，供 UI 展示与审计。

strix 原生链路（``strix.runtime.session_manager``）自己建容器，不经过 ravenholt 的
``service/sandbox/lifecycle.py``。为了不让沙箱在平台里"隐身"，这里在容器就绪后补一条
``SandboxContainer`` 记录：

- 宿主固定为**本机**（strix 的 docker backend 走 ``connect_docker()``，与平台同宿主）；
- 镜像按 ``image_name`` 建/取一条 ``SandboxImage``（``control_proxy_port`` 记为容器内 Caido 端口）；
- ``control_proxy_host_port`` / ``control_proxy_token`` 留空 —— strix 镜像没有 ravenholt 的
  Go 控制面，容器控制台入口会因端口为 0 自动隐藏，列表与展示照常。

回写失败由调用方吞掉（只影响展示，不阻断渗透任务）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import select

from database import get_async_session
from model.sandbox.containers import SandboxContainer
from model.sandbox.images import SandboxImage
from schema.sandbox.containers import SandboxContainerEgressMode, SandboxContainerStatus
from service.host.hosts import ensure_local_managed_host


# 容器内 Caido 监听端口（与 strix ``session_manager`` 的 ``_CONTAINER_CAIDO_PORT`` 对齐）。
_PROVISIONED_CAIDO_PORT = 48080


async def record_provisioned_container(
    *,
    owner_id: int,
    image_name: str,
    container_hash: str,
    container_name: str,
    port_mappings: list[dict[str, Any]] | None = None,
) -> int | None:
    """写入/更新一条由 strix 运行时自建容器的平台记录，返回记录 id。"""
    host = await ensure_local_managed_host()

    async with get_async_session() as session:
        existing = (await session.exec(
            select(SandboxContainer).where(SandboxContainer.container_hash == container_hash)
        )).first()

        image = (await session.exec(
            select(SandboxImage).where(SandboxImage.image_name == image_name)
        )).first()
        if image is None:
            now = datetime.now()
            image = SandboxImage(
                image_name=image_name,
                control_proxy_port=_PROVISIONED_CAIDO_PORT,
                supports_tor=False,
                created_at=now,
                updated_at=now,
            )
            session.add(image)
            await session.commit()
            await session.refresh(image)

        now = datetime.now()
        if existing is not None:
            existing.status = SandboxContainerStatus.RUNNING
            existing.container_name = container_name or existing.container_name
            if port_mappings:
                existing.port_mappings = port_mappings
            existing.updated_at = now
            session.add(existing)
            await session.commit()
            return existing.id

        record = SandboxContainer(
            host_id=host.id or 1,
            container_name=container_name,
            container_hash=container_hash,
            owner_id=owner_id,
            image_id=image.id or 0,
            egress_mode=SandboxContainerEgressMode.DIRECT,
            control_proxy_host_port=0,
            control_proxy_token="",
            port_mappings=port_mappings or [],
            status=SandboxContainerStatus.RUNNING,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


__all__ = ["record_provisioned_container"]
