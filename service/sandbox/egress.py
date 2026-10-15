import os
from dataclasses import dataclass

from model.egress_proxy.proxies import EgressProxy
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import SandboxContainerEgressMode
from service.egress_proxy.proxies import egress_proxy_upstream


NO_PROXY_VALUE = "localhost,127.0.0.1,::1"
# Ravenholt 的运行时出网代理（容器内 127.0.0.1:8118）由镜像内置的 Go 控制面提供；ravenholt 官方
# 沙箱镜像没有该控制面。默认不再注入指向 8118 的代理环境，否则会把沙箱全部出网请求指向
# 一个不存在的代理、直接弄坏出网。如需容器内运行时代理，显式设置该环境变量。
RUNTIME_PROXY_URL_ENV = "SANDBOX_EGRESS_RUNTIME_PROXY_URL"
EGRESS_UPSTREAM_TYPE_ENV = "SANDBOX_EGRESS_UPSTREAM_TYPE"
EGRESS_UPSTREAM_ADDR_ENV = "SANDBOX_EGRESS_UPSTREAM_ADDR"


@dataclass(frozen=True)
class SandboxEgressSelection:
    mode: SandboxContainerEgressMode
    proxy: EgressProxy | None = None


def sandbox_runtime_proxy_environment() -> dict[str, str]:
    proxy_url = os.environ.get(RUNTIME_PROXY_URL_ENV, "").strip()
    if not proxy_url:
        return {}
    return {
        "HTTP_PROXY": proxy_url,
        "http_proxy": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "https_proxy": proxy_url,
        "ALL_PROXY": proxy_url,
        "all_proxy": proxy_url,
        "NO_PROXY": NO_PROXY_VALUE,
        "no_proxy": NO_PROXY_VALUE,
    }


def sandbox_egress_upstream_environment(selection: SandboxEgressSelection) -> dict[str, str]:
    if selection.mode == SandboxContainerEgressMode.DIRECT:
        return {
            EGRESS_UPSTREAM_TYPE_ENV: "",
            EGRESS_UPSTREAM_ADDR_ENV: "",
        }
    if selection.mode == SandboxContainerEgressMode.TOR:
        return {
            EGRESS_UPSTREAM_TYPE_ENV: SandboxContainerEgressMode.TOR.value,
            EGRESS_UPSTREAM_ADDR_ENV: "",
        }
    if selection.proxy is None:
        raise ValueError("managed proxy is required for proxy egress mode")
    return {
        EGRESS_UPSTREAM_TYPE_ENV: selection.proxy.proxy_type.value,
        EGRESS_UPSTREAM_ADDR_ENV: egress_proxy_upstream(selection.proxy),
    }


def sandbox_egress_container_environment(selection: SandboxEgressSelection) -> dict[str, str]:
    return {
        **sandbox_runtime_proxy_environment(),
        **sandbox_egress_upstream_environment(selection),
    }


def sandbox_egress_label(container: SandboxContainer, proxy: EgressProxy | None) -> str:
    if container.egress_mode == SandboxContainerEgressMode.DIRECT:
        return SandboxContainerEgressMode.DIRECT.value
    if container.egress_mode == SandboxContainerEgressMode.TOR:
        return SandboxContainerEgressMode.TOR.value
    if proxy is None:
        return ""
    return f"{proxy.proxy_type.value}://{proxy.proxy_host}:{proxy.proxy_port}"
