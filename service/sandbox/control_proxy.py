from dataclasses import dataclass

from sqlmodel import select

from database import get_async_session
from model.egress_proxy.proxies import EgressProxy
from model.host.hosts import ManagedHost
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerEgressMode, SandboxContainerStatus
from service.sandbox.egress import (
    SandboxEgressSelection,
    sandbox_egress_container_environment,
)


@dataclass(frozen=True)
class SandboxControlProxyTarget:
    container_id: int
    base_url: str
    ws_base_url: str
    token: str
    status: SandboxContainerStatus


async def resolve_sandbox_control_proxy_target(
    container_id: int,
    *,
    require_running: bool = False,
) -> SandboxControlProxyTarget | None:
    async with get_async_session() as session:
        row = (await session.exec(
            select(SandboxContainer, ManagedHost)
            .join(ManagedHost, SandboxContainer.host_id == ManagedHost.id)
            .where(SandboxContainer.id == container_id)
        )).first()
        if row is None:
            return None
        container, host = row

    if container.control_proxy_host_port <= 0 or not container.control_proxy_token:
        return None
    if require_running and container.status != SandboxContainerStatus.RUNNING:
        return None

    base = f"http://{host.ip_address}:{container.control_proxy_host_port}"
    return SandboxControlProxyTarget(
        container_id=container.id or container_id,
        base_url=base,
        ws_base_url=f"ws://{host.ip_address}:{container.control_proxy_host_port}",
        token=container.control_proxy_token,
        status=container.status,
    )


async def resolve_container_egress_environment(container_id: int) -> dict[str, str]:
    async with get_async_session() as session:
        row = (await session.exec(
            select(SandboxContainer, EgressProxy)
            .outerjoin(EgressProxy, SandboxContainer.egress_proxy_id == EgressProxy.id)
            .where(SandboxContainer.id == container_id)
        )).first()
    if row is None:
        raise ValueError("sandbox container not found")
    container, proxy = row
    return sandbox_egress_container_environment(SandboxEgressSelection(
        mode=container.egress_mode,
        proxy=proxy,
    ))


async def apply_container_egress(container_id: int) -> None:
    # 延迟导入：避免 core ←→ service 的导入环
    from core.policy import PolicyDenied, enforce

    target = await resolve_sandbox_control_proxy_target(container_id, require_running=True)
    if target is None:
        raise ValueError("sandbox container is not running")
    environment = await resolve_container_egress_environment(container_id)
    upstream = environment.get("SANDBOX_EGRESS_UPSTREAM_ADDR", "")
    decision = await enforce(
        "egress.apply",
        upstream or None,
        detail={"surface": "platform-egress", "container_id": container_id},
    )
    if not decision.allowed:
        raise PolicyDenied(decision)
    await apply_egress_environment(target, environment)


async def apply_managed_proxy_egress_to_running_containers(egress_proxy_id: int) -> list[int]:
    async with get_async_session() as session:
        container_ids = list((await session.exec(
            select(SandboxContainer.id)
            .where(SandboxContainer.egress_mode == SandboxContainerEgressMode.PROXY)
            .where(SandboxContainer.egress_proxy_id == egress_proxy_id)
            .where(SandboxContainer.status == SandboxContainerStatus.RUNNING)
        )).all())

    failed: list[int] = []
    for container_id in container_ids:
        if container_id is None:
            continue
        try:
            await apply_container_egress(container_id)
        except Exception:
            failed.append(container_id)
    return failed


async def apply_egress_environment(target: SandboxControlProxyTarget, environment: dict[str, str]) -> None:
    # ravenholt 一体化沙箱镜像自带容器内 Go 控制面（sandbox/proxy），它提供
    # ``POST /egress``（见 sandbox/proxy/main.go 的 handleEgress）用于**运行时**
    # 刷新出网环境，并同步重写 /etc/profile.d/sandbox-egress.sh 供后续 shell 会话生效。
    # 控制面端口已由 docker create 发布到宿主（control_proxy_host_port），故从宿主侧调用。
    import asyncio
    import httpx

    if not environment:
        return
    # 容器刚 start 时控制面可能还没监听（entrypoint → supervisord → sandbox-proxy
    # 需要几秒），故带短重试；UI 切 egress 时容器早已 running，重试不产生额外等待。
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, 4):
            try:
                response = await client.post(
                    f"{target.base_url}/egress",
                    json={"environment": environment},
                    headers={"X-Sandbox-Token": target.token},
                )
                response.raise_for_status()
                return
            except Exception as exc:  # noqa: BLE001 - 就绪前的连接失败都值得重试
                last_error = exc
                await asyncio.sleep(2.0 * attempt)
    raise RuntimeError(f"failed to apply sandbox egress: {last_error}") from last_error
