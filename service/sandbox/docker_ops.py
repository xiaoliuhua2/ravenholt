from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

import docker

from logger import get_logger
from schema.sandbox.containers import SandboxContainerPortMapping, SandboxContainerStatus
from model.host.hosts import ManagedHost
from service.host.docker import docker_client_for_host


logger = get_logger(__name__)

# 容器保活命令：Ravenholt 原镜像靠 supervisord 常驻；ravenholt 官方沙箱镜像的
# docker-entrypoint.sh 执行完即退出（镜像没有常驻 CMD），必须显式给一个
# 常驻命令容器才会保持 running。可用 SANDBOX_CONTAINER_COMMAND 覆盖，设为空串则不注入。
_CONTAINER_COMMAND = os.environ.get("SANDBOX_CONTAINER_COMMAND", "sleep infinity")


@dataclass(frozen=True)
class DockerContainerState:
    exists: bool
    status: str = ""


def _resolve_container_command() -> list[str] | None:
    value = _CONTAINER_COMMAND.strip()
    return shlex.split(value) if value else None


def _sandbox_resource_limits() -> dict[str, object]:
    """Tier-1：把策略里的容器资源上限注入 docker create。"""
    from core.policy import get_policy, policy_loaded

    if not policy_loaded():
        return {}
    sandbox = get_policy().sandbox
    return {
        "mem_limit": f"{sandbox.memory_mb}m",
        "nano_cpus": int(sandbox.cpu_cores * 1_000_000_000),
        "pids_limit": sandbox.pids_limit,
    }


def _to_docker_ports(port_mappings: list[SandboxContainerPortMapping]) -> dict[str, tuple[str, int]] | None:
    if not port_mappings:
        return None
    return {
        f"{mapping.container_port}/{mapping.protocol}": ("0.0.0.0", mapping.host_port)
        for mapping in port_mappings
    }


def create_container_sync(
    host: ManagedHost,
    image_ref: str,
    container_name_prefix: str,
    port_mappings: list[SandboxContainerPortMapping],
    environment: dict[str, str] | None = None,
    command: list[str] | None = None,
) -> tuple[str, str]:
    client = docker_client_for_host(host)
    try:
        create_kwargs = {
            "image": image_ref,
            "ports": _to_docker_ports(port_mappings),
            "stdin_open": True,
            "tty": False,
        }
        create_kwargs.update(_sandbox_resource_limits())
        if environment:
            create_kwargs["environment"] = environment
        resolved_command = command if command is not None else _resolve_container_command()
        if resolved_command:
            create_kwargs["command"] = resolved_command

        container = client.containers.create(
            **create_kwargs,
        )
        container_name = f"{container_name_prefix}-{container.id[:12]}"
        try:
            container.rename(container_name)
        except Exception:
            container.remove(force=True)
            raise
        return container.id, container_name
    finally:
        client.close()


def inspect_container_state_sync(host: ManagedHost, container_hash: str) -> DockerContainerState:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.reload()
        return DockerContainerState(exists=True, status=str(container.status or ""))
    except docker.errors.NotFound:
        return DockerContainerState(exists=False)
    finally:
        client.close()


def start_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.start()
    finally:
        client.close()


def stop_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.stop()
    finally:
        client.close()


def remove_container_sync(host: ManagedHost, container_hash: str) -> None:
    client = docker_client_for_host(host)
    try:
        container = client.containers.get(container_hash)
        container.remove(force=True)
    except docker.errors.NotFound:
        logger.debug("sandbox container instance already absent: %s", container_hash)
    finally:
        client.close()


def docker_status_to_sandbox_status(status: str) -> SandboxContainerStatus:
    normalized = status.strip().lower()
    if normalized == "running":
        return SandboxContainerStatus.RUNNING
    if normalized == "created":
        return SandboxContainerStatus.CREATED
    if normalized == "exited":
        return SandboxContainerStatus.STOPPED
    return SandboxContainerStatus.ERROR
