"""Caido 侧车端口的反向代理。

Caido 由 strix 以 sidecar 形式提供，容器内监听 48080。默认 bridge 模式下 Docker 把它
发布在宿主 127.0.0.1 上；macvlan 模式下容器改用自身 IP，由部署者在宿主侧保证可达。
两种地址都不是浏览器能直连的，因此由后端按路径前缀反代（上游主机地址从容器记录的端口
映射里读，见 ``caido_upstream_host``）。

Caido 前端的所有资源与接口都用相对路径推导（index.html 里是 ``./assets/...``，GraphQL 请求
与重定向也都是相对路径，代码里没有出现 ``location.origin``），所以前缀反代不需要改写响应体，
只要求入口 URL 以 ``/`` 结尾，否则相对路径会退化到上一层前缀。

实测（Caido 0.56.0）：主界面只用 HTTP + GraphQL 轮询取数，不建立 WebSocket / SSE，因此这里
只做 HTTP 转发。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from database import get_async_session
from logger import get_logger
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerStatus


logger = get_logger(__name__)

# 沙箱容器内 Caido 侧车端口，与 core.strix_runtime.sandbox_provision.CONTAINER_CAIDO_PORT 对齐
CAIDO_CONTAINER_PORT = 48080
# 侧车端口发布在宿主回环地址上，只有平台进程自己连得上
CAIDO_UPSTREAM_HOST = "127.0.0.1"

_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# 逐跳首部不能透传；内容编码与长度也不能原样透传（响应体已被 httpx 解码，长度随之变化）
_SKIP_REQUEST_HEADERS = {
    "host",
    "connection",
    "content-length",
    "accept-encoding",
    "upgrade",
}
_SKIP_RESPONSE_HEADERS = {
    "transfer-encoding",
    "connection",
    "content-encoding",
    "content-length",
}


@dataclass(frozen=True)
class CaidoProxyTarget:
    container_id: int
    host_port: int
    host: str = CAIDO_UPSTREAM_HOST

    @property
    def http_base(self) -> str:
        return f"http://{self.host}:{self.host_port}"


async def resolve_caido_target(container_id: int) -> CaidoProxyTarget | None:
    """从容器记录的端口映射里解析 Caido 反代目标。

    容器未运行或没有该端口映射时直接判定为「没有抓包入口」，避免把上游不可达变成 502
    —— 端口只在容器创建时发布，容器停了端口也就没了。
    """
    async with get_async_session() as session:
        container = await session.get(SandboxContainer, container_id)
    if container is None or container.status != SandboxContainerStatus.RUNNING:
        return None

    host_port = caido_host_port(container.port_mappings or [])
    if host_port <= 0:
        return None
    return CaidoProxyTarget(
        container_id=container_id,
        host_port=host_port,
        host=caido_upstream_host(container.port_mappings or []),
    )


def caido_upstream_host(port_mappings: list[Any]) -> str:
    """解析 Caido 侧车端口对应的上游主机地址。

    端口映射的 ``host`` 字段记录容器内 Caido 的宿主可达地址：默认 bridge 模式下发布在
    宿主回环（127.0.0.1），macvlan 模式下则是容器自身 IP。字段缺失时回退宿主回环，兼容
    改造前写入的历史记录。
    """
    for mapping in port_mappings:
        if _field(mapping, "container_port") != CAIDO_CONTAINER_PORT:
            continue
        if (_field(mapping, "protocol") or "tcp") != "tcp":
            continue
        host = _field(mapping, "host")
        if isinstance(host, str) and host.strip():
            return host.strip()
        return CAIDO_UPSTREAM_HOST
    return CAIDO_UPSTREAM_HOST


def caido_host_port(port_mappings: list[Any]) -> int:
    """在端口映射中找 Caido 侧车端口对应的宿主端口，找不到返回 0。"""
    for mapping in port_mappings:
        if _field(mapping, "container_port") != CAIDO_CONTAINER_PORT:
            continue
        if (_field(mapping, "protocol") or "tcp") != "tcp":
            continue
        try:
            return int(_field(mapping, "host_port") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def build_upstream_url(base: str, path: str, query: str) -> str:
    suffix = f"/{path.lstrip('/')}" if path else "/"
    return f"{base}{suffix}{f'?{query}' if query else ''}"


async def proxy_caido_http(
    target: CaidoProxyTarget,
    path: str,
    *,
    method: str,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> httpx.Response:
    """把一次 HTTP 请求转发到 Caido；不跟随重定向，Location 原样交回浏览器相对解析。"""
    url = build_upstream_url(target.http_base, path, query)
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=False) as client:
        return await client.request(
            method,
            url,
            headers=filter_headers(headers or {}, _SKIP_REQUEST_HEADERS),
            content=body or None,
        )


def filter_response_headers(headers: Any) -> dict[str, str]:
    return filter_headers(headers, _SKIP_RESPONSE_HEADERS)


def filter_headers(headers: Any, skip: set[str]) -> dict[str, str]:
    items = headers.items() if hasattr(headers, "items") else headers
    return {key: value for key, value in items if key.lower() not in skip}


def _field(mapping: Any, name: str) -> Any:
    if isinstance(mapping, dict):
        return mapping.get(name)
    return getattr(mapping, name, None)
