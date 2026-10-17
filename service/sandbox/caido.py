"""平台「沙箱容器」的 Caido 初始化（bootstrap）。

strix 会话路径在 provision 时会 bootstrap Caido —— 见 ``strix/runtime/caido_bootstrap.py``：
容器内取 guest token，再用 ``caido_sdk_client`` 建一个临时 project 并选中。平台「沙箱容器」
是独立的 docker-py 生命周期（``service/sandbox/lifecycle.py``），不经 strix session，所以这里
补齐同一件事；否则 Caido 作为 HTTP 代理会返回 500（没有选中 project），控制台里的抓包链路等于废的。

实现刻意与 ``strix/runtime/caido_bootstrap.py`` 对齐：同样的 LoginAsGuest mutation、同样的
SDK 调用序列（connect → project.create → project.select）。差别只在取 token 的方式——那边用
``session.exec`` 在容器内 curl，这里直接从宿主访问容器 IP（Caido 监听 0.0.0.0:48080）。

失败一律 best-effort：只记日志，不阻断容器启动。
"""

from __future__ import annotations

import asyncio

from logger import get_logger
from model.host.hosts import ManagedHost


logger = get_logger(__name__)

CAIDO_CONTAINER_PORT = 48080
_LOGIN_AS_GUEST_BODY = (
    '{"query":"mutation LoginAsGuest { loginAsGuest { token { accessToken } } }"}'
)
# Caido 的 GraphQL 监听可能晚于容器启动就绪，重试循环兼作 readiness 探测。
_READY_ATTEMPTS = 15


def container_ip_sync(host: ManagedHost, container_hash: str) -> str:
    """取容器在任意网络下的 IPv4 地址（macvlan 独立 IP 或 bridge IP）。"""
    from service.host.docker import docker_client_for_host

    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.reload()
        networks = ((container.attrs or {}).get("NetworkSettings") or {}).get("Networks") or {}
        for entry in networks.values():
            address = str((entry or {}).get("IPAddress") or "").strip()
            if address:
                return address
        return ""
    finally:
        client.close()


async def _login_as_guest(base_url: str) -> str:
    import httpx

    last_error: str = "unknown"
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, _READY_ATTEMPTS + 1):
            try:
                response = await client.post(
                    f"{base_url}/graphql",
                    content=_LOGIN_AS_GUEST_BODY,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    payload = response.json()
                    token = (
                        ((payload.get("data") or {}).get("loginAsGuest") or {})
                        .get("token") or {}
                    ).get("accessToken")
                    if token:
                        return str(token)
                    last_error = f"loginAsGuest returned no token: {payload}"
                else:
                    last_error = f"HTTP {response.status_code}"
            except Exception as exc:  # noqa: BLE001 - 探测性重试，任何异常都继续
                last_error = repr(exc)
            await asyncio.sleep(min(2.0 * attempt, 8.0))
    raise RuntimeError(f"loginAsGuest failed after {_READY_ATTEMPTS} attempts: {last_error}")


async def bootstrap_container_caido(host: ManagedHost, container_hash: str) -> bool:
    """为平台沙箱容器准备 Caido project。成功返回 True；失败只记日志返回 False。"""
    ip = await asyncio.to_thread(container_ip_sync, host, container_hash)
    if not ip:
        logger.warning("sandbox container %s has no reachable IP; skip caido bootstrap", container_hash[:12])
        return False

    base_url = f"http://{ip}:{CAIDO_CONTAINER_PORT}"
    try:
        access_token = await _login_as_guest(base_url)

        from caido_sdk_client import Client, TokenAuthOptions
        from caido_sdk_client.types import CreateProjectOptions

        client = Client(base_url, auth=TokenAuthOptions(token=access_token))
        try:
            await client.connect()
            project = await client.project.create(
                CreateProjectOptions(name="sandbox", temporary=True),
            )
            await client.project.select(project.id)
            logger.info("sandbox container %s: caido project %s selected", container_hash[:12], project.id)
        finally:
            try:
                await client.aclose()
            except Exception:
                logger.debug("caido client aclose failed", exc_info=True)
        return True
    except Exception:
        logger.warning("caido bootstrap failed for sandbox container %s", container_hash[:12], exc_info=True)
        return False
