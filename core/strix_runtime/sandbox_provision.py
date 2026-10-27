"""沙箱提供层：为一次 ravenholt 会话拉起 strix 原生沙箱（含容器内 Caido）。

职责边界：
- 建容器、起 Caido、解析宿主可达的 Caido 端口 —— 全部复用 strix 的
  ``strix.runtime.session_manager.create_or_reuse``，**不重造**；
- 沙箱创建前过 ravenholt 红线闸口（``container.create``，与
  ``service/sandbox/lifecycle.py`` 同一 action）；
- 把 SDK 会话包上红线闸口（``core.strix_runtime.gated_session``）；
- 回写一条 ``SandboxContainer`` 记录供 UI 展示（best-effort，失败不阻断 run）。

容器由 strix 的 docker backend 建（保留镜像 ENTRYPOINT 以便容器内 Caido 启动，
并追加 NET_ADMIN/NET_RAW），因此 ravenholt 侧的 docker-py 控制面不参与。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.policy.enforcer import enforce
from core.strix_runtime.gated_session import bind_policy_gate


logger = logging.getLogger(__name__)

# 与 strix ``session_manager`` 对齐：容器内 Caido 监听端口。
CONTAINER_CAIDO_PORT = 48080
# 容器内 Go 控制面端口（终端 / files / noVNC / 出网代理），端口映射同样写进记录。
CONTAINER_CONTROL_PORT = 8000


class SandboxProvisionError(RuntimeError):
    """沙箱提供失败（红线拒绝、建容器失败、端口不可达等）。"""


@dataclass(frozen=True, slots=True)
class SandboxProvisionResult:
    client: Any
    session: Any
    caido_client: Any
    container_hash: str
    container_name: str
    image_name: str
    record_id: int | None = None
    # 容器内 Caido 的宿主可达端点（由 strix 的 exposed-port 解析给出），供平台展示与跳转。
    caido_host: str = ""
    caido_port: int = 0


def _resolve_image_name(image_name: str | None) -> str:
    """确定沙箱镜像：显式入参 > 环境变量 > strix 默认。

    必须在**首次** ``load_settings()`` 之前把 ``STRIX_IMAGE`` 落到环境里 ——
    strix 的 settings 是 memo 的（``strix/config/loader.py:36-52``），晚设无效；
    同时 ``create_or_reuse`` 也会收到显式 ``image``，双保险。
    """
    if image_name:
        os.environ.setdefault("STRIX_IMAGE", image_name)
        return image_name

    configured = os.environ.get("STRIX_IMAGE", "").strip()
    if configured:
        return configured

    from strix.config import load_settings

    image = str(load_settings().runtime.image or "").strip()
    if not image:
        raise SandboxProvisionError("no sandbox image configured (set STRIX_IMAGE)")
    os.environ.setdefault("STRIX_IMAGE", image)
    return image


def _session_container(session: Any) -> tuple[str, str]:
    """从 SDK 会话取容器 id 与名字（尽力而为，取不到返回空串）。"""
    inner = getattr(session, "_inner", None)
    container = getattr(inner, "_container", None)
    container_id = getattr(getattr(inner, "state", None), "container_id", "") or ""
    if not container_id:
        container_id = getattr(container, "id", "") or ""
    name = getattr(container, "name", "") or ""
    return str(container_id), str(name)


def _session_publisher(session_id: str):
    """构造「把事件推进本会话事件总线」的回调，供闸口挂起时落审批卡片。

    延迟 import ``core.runtime.session``：装配层与运行时之间避免模块级环依赖
    （``service/agent/subordinates.py`` 是同一手法）。
    """

    def _publish(event: Any) -> bool:
        from core.runtime.session import get_agent_pool

        return bool(get_agent_pool().publish(session_id, event))

    return _publish


async def provision_sandbox(
    *,
    session_id: str,
    owner_id: int,
    image_name: str | None = None,
    local_sources: list[dict[str, Any]] | None = None,
) -> SandboxProvisionResult:
    """拉起（或复用）本次会话的沙箱，返回绑定闸口后的会话与 Caido 句柄。

    ``local_sources`` 用于源码审计：把宿主上的源码目录 bind-mount 进容器
    ``/workspace/<workspace_subdir>``（条目格式见 strix ``session_manager``）。

    失败一律抛 :class:`SandboxProvisionError`，由调用方决定降级策略；红线拒绝
    （``container.create``）同样按失败处理（fail-closed）。
    """
    image = _resolve_image_name(image_name)

    decision = await enforce(
        "container.create",
        None,
        detail={"session_id": session_id, "image": image, "surface": "strix-runtime"},
    )
    if not decision.allowed:
        raise SandboxProvisionError(
            f"[{decision.code}] 红线策略拒绝创建沙箱容器：{decision.reason}"
        )

    from strix.runtime.session_manager import create_or_reuse

    try:
        bundle = await create_or_reuse(
            session_id,
            image=image,
            local_sources=local_sources or [],
            extra_files=None,
        )
    except Exception as exc:  # noqa: BLE001 - 统一收敛成可降级的提供失败
        raise SandboxProvisionError(f"failed to bring up sandbox session: {exc}") from exc

    session = bundle.get("session")
    if session is None:
        raise SandboxProvisionError("strix session bundle has no session")

    caido_host, caido_port = await _resolve_exposed_endpoint(session, CONTAINER_CAIDO_PORT)
    control_host, control_port = await _resolve_exposed_endpoint(session, CONTAINER_CONTROL_PORT)
    gated = bind_policy_gate(session, session_id=session_id, publisher=_session_publisher(session_id))
    container_hash, container_name = _session_container(gated)

    result = SandboxProvisionResult(
        client=bundle.get("client"),
        session=gated,
        caido_client=bundle.get("caido_client"),
        container_hash=container_hash,
        container_name=container_name,
        image_name=image,
        caido_host=caido_host,
        caido_port=caido_port,
    )
    logger.info(
        "provisioned sandbox for session=%s image=%s container=%s caido=%s",
        session_id,
        image,
        container_hash[:12] or "?",
        f"{caido_host}:{caido_port}" if caido_port else "?",
    )

    record_id = await _record_container_best_effort(
        owner_id=owner_id,
        image_name=image,
        container_hash=container_hash,
        container_name=container_name,
        port_mappings=[
            *_port_mapping(CONTAINER_CAIDO_PORT, caido_host, caido_port),
            *_port_mapping(CONTAINER_CONTROL_PORT, control_host, control_port),
        ],
        control_proxy_token=str(bundle.get("control_proxy_token") or ""),
    )
    return SandboxProvisionResult(
        client=result.client,
        session=result.session,
        caido_client=result.caido_client,
        container_hash=result.container_hash,
        container_name=result.container_name,
        image_name=result.image_name,
        record_id=record_id,
        caido_host=result.caido_host,
        caido_port=result.caido_port,
    )


async def _resolve_exposed_endpoint(session: Any, port: int) -> tuple[str, int]:
    """解析容器内某端口对平台可达的端点（strix 已把该端口暴露出来）。

    解析失败不阻断 provision —— 这些入口只用于展示、跳转与反代，拿不到就不给入口。
    """
    try:
        endpoint = await session.resolve_exposed_port(port)
    except Exception:  # noqa: BLE001 - 端口解析失败不影响沙箱可用性
        logger.warning("resolve exposed host endpoint failed port=%s", port, exc_info=True)
        return "", 0
    host = str(getattr(endpoint, "host", "") or "")
    try:
        exposed_port = int(getattr(endpoint, "port", 0) or 0)
    except (TypeError, ValueError):
        exposed_port = 0
    return host, exposed_port


def _port_mapping(container_port: int, host: str, host_port: int) -> list[dict[str, Any]]:
    if host_port <= 0:
        return []
    return [{
        "container_port": container_port,
        "host_port": host_port,
        # 上游主机地址：bridge 模式下为宿主回环 127.0.0.1，macvlan 模式下为容器 IP。
        # 反代（service.sandbox.caido / control_proxy）按它连接，避免误把容器 IP 当作宿主回环。
        "host": host,
        "protocol": "tcp",
    }]


async def cleanup_sandbox(session_id: str) -> None:
    """回收本次会话的沙箱容器（仅在会话终态调用，勿按 turn 调用）。

    ``_SESSION_CACHE`` 靠 scan_id 复用容器与 Caido，逐轮清理会打断跨轮连续性；
    因此这里只做「终态清理」：销毁容器（对应记录由 delete_session 一并销账）。
    """
    from strix.runtime.session_manager import cleanup

    try:
        await cleanup(session_id)
    except Exception:  # noqa: BLE001 - 回收失败不得影响会话收尾
        logger.warning("strix sandbox cleanup failed session=%s", session_id, exc_info=True)


async def _record_container_best_effort(
    *,
    owner_id: int,
    image_name: str,
    container_hash: str,
    container_name: str,
    port_mappings: list[dict[str, Any]] | None = None,
    control_proxy_token: str = "",
) -> int | None:
    if not container_hash:
        logger.warning("skip sandbox record write-back: container id unavailable")
        return None
    try:
        from service.sandbox.provision import record_provisioned_container

        return await record_provisioned_container(
            owner_id=owner_id,
            image_name=image_name,
            container_hash=container_hash,
            container_name=container_name,
            port_mappings=port_mappings,
            control_proxy_token=control_proxy_token,
        )
    except Exception:  # noqa: BLE001 - 回写失败只影响展示，不阻断 run
        logger.warning("sandbox container record write-back failed", exc_info=True)
        return None


__all__ = [
    "CONTAINER_CAIDO_PORT",
    "SandboxProvisionError",
    "SandboxProvisionResult",
    "cleanup_sandbox",
    "provision_sandbox",
]
