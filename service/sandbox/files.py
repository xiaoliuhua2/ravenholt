from __future__ import annotations

import asyncio
import base64 as base64_module
import io
import posixpath
import tarfile
from collections.abc import AsyncIterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO

import docker
from sqlmodel import select

from database import get_async_session
from model.host.hosts import ManagedHost
from model.sandbox.containers import SandboxContainer
from schema.sandbox.containers import (
    ContainerFileInfo,
    ContainerFileType,
    ContainerFileUploadItem,
    SandboxContainerStatus,
)


# ravenholt 官方沙箱镜像没有 Ravenholt 容器内的 Go 控制面（HTTP /files*），
# 文件能力改为直接通过 docker-py 操作目标容器：目录/属性用容器内 shell（find/stat），
# 读写/上传用 Docker archive API（get_archive / put_archive），其余用 exec_run 拼命令。
_FIND_FORMAT = "'%f\\0%y\\0%s\\0%T@\\0%u\\0%g\\0%m\\0%p\\0'"
_DOWNLOAD_CHUNK_SIZE = 65536
_TYPE_BY_CHAR = {b"d": ContainerFileType.DIRECTORY, b"l": ContainerFileType.SYMLINK}


@dataclass(frozen=True)
class ContainerUploadSource:
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class ContainerDownloadStream:
    filename: str
    media_type: str
    chunks: AsyncIterator[bytes]


@dataclass(frozen=True)
class _DockerTarget:
    host: ManagedHost
    container_hash: str
    status: SandboxContainerStatus


async def close_file_http_client() -> None:
    # 旧的 Go 控制面 HTTP 客户端已移除，保留空实现以兼容既有调用方。
    return None


async def resolve_file_container_status(id: int) -> SandboxContainerStatus | None:
    target = await _resolve_docker_target(id)
    return None if target is None else target.status


async def list_container_files(container_id: int, path: str) -> list[ContainerFileInfo]:
    target = await _require_running_target(container_id)
    return await asyncio.to_thread(_list_container_files_sync, target, _normalize_container_path(path))


async def get_container_file_info(container_id: int, path: str) -> ContainerFileInfo | None:
    target = await _require_running_target(container_id)
    return await asyncio.to_thread(_get_container_file_info_sync, target, _normalize_container_path(path))


async def read_container_file(container_id: int, path: str, max_bytes: int = 1_048_576, *, base64_mode: bool = False) -> str:
    target = await _require_running_target(container_id)
    return await asyncio.to_thread(
        _read_container_file_sync,
        target,
        _normalize_container_path(path),
        max_bytes,
        base64_mode,
    )


_MAX_FILE_GATE_CHARS = 200_000

# 平台对沙箱容器的文件操作映射：这些都是**容器内的产物操作**（建任务根、写报告、
# 上传附件），不是对渗透目标的操作，因此统一归 sandbox_file —— 常规动作、默认放行，
# 不进 src-hunt §2 的风险审批项。
_FILE_ACTION_BY_OP = {
    "upload": "sandbox.file.upload",
    "download": "sandbox.file.download",
    "write": "sandbox.file.write",
    "write-bytes": "sandbox.file.write",
    "copy": "sandbox.file.write",
    "mkdir": "sandbox.file.write",
    "move": "sandbox.file.write",
    "delete": "sandbox.file.write",
}


async def _enforce_file_write(op: str, container_id: int, content: str, paths: list[str]) -> None:
    """文件操作前的红线判定（kill switch / 禁测清单 / 载荷上限 / 限速）。"""
    from core.policy import PolicyDenied, enforce

    text = content[:_MAX_FILE_GATE_CHARS] if content else " ".join(paths)
    decision = await enforce(
        _FILE_ACTION_BY_OP.get(op, "sandbox.file.write"),
        None,
        payload_bytes=len(text.encode("utf-8")),
        payload_text=content[:_MAX_FILE_GATE_CHARS],
        detail={
            "surface": "platform-files",
            "op": op,
            "container_id": container_id,
            "paths": paths[:20],
        },
    )
    if not decision.allowed:
        raise PolicyDenied(decision)


async def upload_container_files(
    container_id: int,
    path: str,
    sources: list[ContainerUploadSource],
    overwrite: bool,
) -> list[ContainerFileUploadItem]:
    await _enforce_file_write("upload", container_id, "", [path])
    target = await _require_running_target(container_id)
    normalized = _normalize_container_path(path)
    try:
        return await asyncio.to_thread(_upload_container_files_sync, target, normalized, sources, overwrite)
    finally:
        for source in sources:
            source.stream.close()


async def download_container_paths(container_id: int, paths: list[str]) -> ContainerDownloadStream:
    await _enforce_file_write("download", container_id, "", paths)
    target = await _require_running_target(container_id)
    normalized = [_normalize_container_path(path) for path in paths]
    if not normalized:
        raise ValueError("download path is required")
    single_file = len(normalized) == 1 and await asyncio.to_thread(
        _path_is_downloadable_file_sync, target, normalized[0]
    )
    if single_file:
        return ContainerDownloadStream(
            filename=posixpath.basename(normalized[0]) or "download",
            media_type="application/octet-stream",
            chunks=_stream_download(target, normalized, single_file=True),
        )
    return ContainerDownloadStream(
        filename="container-files.tar",
        media_type="application/x-tar",
        chunks=_stream_download(target, normalized, single_file=False),
    )


async def write_container_file(container_id: int, path: str, content: str) -> bool:
    await _enforce_file_write("write", container_id, content, [path])
    target = await _require_running_target(container_id)
    await asyncio.to_thread(_write_container_file_sync, target, _normalize_container_path(path), content)
    return True


async def write_container_bytes(container_id: int, path: str, data: bytes) -> bool:
    """写入二进制内容（附件图片等）。文本写入见 ``write_container_file``。"""
    await _enforce_file_write("write-bytes", container_id, "", [path])
    target = await _require_running_target(container_id)
    await asyncio.to_thread(
        _write_container_bytes_sync, target, _normalize_container_path(path), data
    )
    return True


async def copy_container_files(container_id: int, sources: list[str], destination: str) -> bool:
    await _enforce_file_write("copy", container_id, "", [*sources, destination])
    target = await _require_running_target(container_id)
    normalized_sources = [_normalize_container_path(source) for source in sources]
    await asyncio.to_thread(
        _run_file_command,
        target,
        'dest="$1"; shift; mkdir -p -- "$dest" || exit 1; for src in "$@"; do cp -a -- "$src" "$dest/" || exit 1; done',
        _normalize_container_path(destination),
        *normalized_sources,
    )
    return True


async def move_container_files(container_id: int, sources: list[str], destination: str) -> bool:
    await _enforce_file_write("move", container_id, "", [*sources, destination])
    target = await _require_running_target(container_id)
    normalized_sources = [_normalize_container_path(source) for source in sources]
    await asyncio.to_thread(
        _run_file_command,
        target,
        'dest="$1"; shift; mkdir -p -- "$dest" || exit 1; for src in "$@"; do mv -f -- "$src" "$dest/" || exit 1; done',
        _normalize_container_path(destination),
        *normalized_sources,
    )
    return True


async def delete_container_files(container_id: int, paths: list[str]) -> bool:
    await _enforce_file_write("delete", container_id, "", paths)
    target = await _require_running_target(container_id)
    normalized = [_normalize_container_path(path) for path in paths]
    await asyncio.to_thread(
        _run_file_command,
        target,
        'for p in "$@"; do rm -rf -- "$p" || exit 1; done',
        *normalized,
    )
    return True


async def create_container_directory(container_id: int, path: str) -> bool:
    await _enforce_file_write("mkdir", container_id, "", [path])
    target = await _require_running_target(container_id)
    await asyncio.to_thread(
        _run_file_command,
        target,
        'mkdir -p -- "$1"',
        _normalize_container_path(path),
    )
    return True


# ── docker helpers ─────────────────────────────────────────────────────────────


async def _resolve_docker_target(container_id: int, *, require_running: bool = False) -> _DockerTarget | None:
    async with get_async_session() as session:
        row = (await session.exec(
            select(SandboxContainer, ManagedHost)
            .join(ManagedHost, SandboxContainer.host_id == ManagedHost.id)
            .where(SandboxContainer.id == container_id)
        )).first()
        if row is None:
            return None
        container, host = row

    if require_running and container.status != SandboxContainerStatus.RUNNING:
        return None
    return _DockerTarget(host=host, container_hash=container.container_hash, status=container.status)


async def _require_running_target(container_id: int) -> _DockerTarget:
    target = await _resolve_docker_target(container_id, require_running=True)
    if target is None:
        raise FileNotFoundError("sandbox container not found")
    return target


@contextmanager
def _docker_container(target: _DockerTarget):
    from service.host.docker import docker_client_for_host

    client = docker_client_for_host(target.host)
    try:
        container = client.containers.get(target.container_hash)
    except docker.errors.NotFound as exc:
        client.close()
        raise FileNotFoundError("sandbox container not found") from exc
    try:
        yield container
    finally:
        client.close()


def _exec_in_container(container, script: str, *args: str) -> tuple[int, bytes, bytes]:
    exit_code, (stdout, stderr) = container.exec_run(
        ["/bin/sh", "-c", script, "sh", *args],
        demux=True,
    )
    return int(exit_code or 0), stdout or b"", stderr or b""


def _list_container_files_sync(target: _DockerTarget, path: str) -> list[ContainerFileInfo]:
    script = f'find "$1" -mindepth 1 -maxdepth 1 -printf {_FIND_FORMAT}'
    with _docker_container(target) as container:
        exit_code, stdout, stderr = _exec_in_container(container, script, path)
    if exit_code != 0:
        _raise_exec_error(stderr, exit_code)
    return _parse_find_records(stdout)


def _get_container_file_info_sync(target: _DockerTarget, path: str) -> ContainerFileInfo | None:
    script = f'find "$1" -maxdepth 0 -printf {_FIND_FORMAT}'
    with _docker_container(target) as container:
        exit_code, stdout, stderr = _exec_in_container(container, script, path)
    if exit_code != 0:
        if "No such file or directory" in stderr.decode("utf-8", errors="replace"):
            return None
        _raise_exec_error(stderr, exit_code)
    records = _parse_find_records(stdout)
    return records[0] if records else None


def _read_container_file_sync(target: _DockerTarget, path: str, max_bytes: int, base64_mode: bool) -> str:
    script = (
        'if [ -d "$1" ]; then echo "is a directory" >&2; exit 2; fi; '
        'if [ ! -e "$1" ]; then echo "No such file or directory" >&2; exit 3; fi; '
        'head -c "$2" -- "$1" | base64 | tr -d "\\n"'
    )
    with _docker_container(target) as container:
        exit_code, stdout, stderr = _exec_in_container(container, script, path, str(max(0, int(max_bytes))))
    if exit_code != 0:
        _raise_exec_error(stderr, exit_code)
    encoded = stdout.decode("ascii", errors="ignore")
    if base64_mode:
        return encoded
    try:
        raw = base64_module.b64decode(encoded)
    except ValueError:
        raw = b""
    return raw.decode("utf-8", errors="replace")


def _write_container_bytes_sync(target: _DockerTarget, path: str, data: bytes) -> None:
    directory = posixpath.dirname(path) or "/"
    name = posixpath.basename(path)
    if not name:
        raise ValueError("invalid sandbox file path")
    archive = _build_file_tar(name, data, 0o644)
    with _docker_container(target) as container:
        ok = _put_archive(container, directory, archive)
    if not ok:
        raise RuntimeError("failed to write sandbox file")


def _write_container_file_sync(target: _DockerTarget, path: str, content: str) -> None:
    _write_container_bytes_sync(target, path, content.encode("utf-8"))


def _upload_container_files_sync(
    target: _DockerTarget,
    path: str,
    sources: list[ContainerUploadSource],
    overwrite: bool,
) -> list[ContainerFileUploadItem]:
    items: list[ContainerFileUploadItem] = []
    with _docker_container(target) as container:
        if not _path_is_dir(container, path):
            raise FileNotFoundError("path not found")
        for source in sources:
            name = posixpath.basename((source.filename or "").strip()) or "upload"
            payload = source.stream.read()
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            target_path = posixpath.join(path, name)
            if not overwrite and _path_exists(container, target_path):
                raise FileExistsError(f"{name} already exists")
            archive = _build_file_tar(name, payload, 0o644)
            if not _put_archive(container, path, archive):
                raise RuntimeError("failed to upload sandbox file")
            items.append(ContainerFileUploadItem(name=name, path=target_path, size=len(payload)))
    return items


def _path_is_downloadable_file_sync(target: _DockerTarget, path: str) -> bool:
    script = 'if [ -d "$1" ]; then echo d; elif [ -e "$1" ]; then echo f; else echo n; fi'
    with _docker_container(target) as container:
        _exit_code, stdout, _stderr = _exec_in_container(container, script, path)
    kind = stdout.decode("ascii", errors="ignore").strip()
    if kind not in {"d", "f"}:
        raise FileNotFoundError("path not found")
    return kind == "f"


def _download_bytes_sync(target: _DockerTarget, paths: list[str], single_file: bool) -> bytes:
    with _docker_container(target) as container:
        if single_file:
            stream, _stat = container.get_archive(paths[0])
            with tarfile.open(fileobj=stream, mode="r|*") as archive:
                for member in archive:
                    if member.isfile():
                        fileobj = archive.extractfile(member)
                        return fileobj.read() if fileobj is not None else b""
            return b""

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as output:
            for path in paths:
                try:
                    stream, _stat = container.get_archive(path)
                except docker.errors.NotFound:
                    continue
                with tarfile.open(fileobj=stream, mode="r|*") as archive:
                    for member in archive:
                        fileobj = archive.extractfile(member) if member.isfile() else None
                        output.addfile(member, fileobj)
        return buffer.getvalue()


async def _stream_download(target: _DockerTarget, paths: list[str], *, single_file: bool) -> AsyncIterator[bytes]:
    data = await asyncio.to_thread(_download_bytes_sync, target, paths, single_file)
    for start in range(0, len(data), _DOWNLOAD_CHUNK_SIZE):
        yield data[start:start + _DOWNLOAD_CHUNK_SIZE]


def _run_file_command(target: _DockerTarget, script: str, *args: str) -> None:
    with _docker_container(target) as container:
        exit_code, _stdout, stderr = _exec_in_container(container, script, *args)
    if exit_code != 0:
        _raise_exec_error(stderr, exit_code)


def _path_is_dir(container, path: str) -> bool:
    _exit_code, stdout, _stderr = _exec_in_container(container, 'if [ -d "$1" ]; then echo 1; fi', path)
    return stdout.decode("ascii", errors="ignore").strip() == "1"


def _path_exists(container, path: str) -> bool:
    _exit_code, stdout, _stderr = _exec_in_container(container, 'if [ -e "$1" ]; then echo 1; fi', path)
    return stdout.decode("ascii", errors="ignore").strip() == "1"


def _put_archive(container, path: str, archive: bytes) -> bool:
    try:
        return bool(container.put_archive(path, archive))
    except docker.errors.NotFound as exc:
        raise FileNotFoundError("path not found") from exc


def _build_file_tar(name: str, data: bytes, mode: int) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        info.mode = mode
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


# ── parsing helpers ────────────────────────────────────────────────────────────


def _normalize_container_path(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return "/"
    cleaned = posixpath.normpath("/" + raw.lstrip("/"))
    return "/" if cleaned in (".", "") else cleaned


def _parse_find_records(output: bytes) -> list[ContainerFileInfo]:
    fields = output.split(b"\x00")
    if fields and fields[-1] == b"":
        fields.pop()
    files: list[ContainerFileInfo] = []
    for index in range(0, len(fields) - 7, 8):
        name, type_char, size, modified, owner, group, mode, path = fields[index:index + 8]
        files.append(ContainerFileInfo(
            name=_decode_text(name),
            type=_TYPE_BY_CHAR.get(type_char, ContainerFileType.FILE),
            size=_parse_int(size),
            modified_at=_parse_timestamp(modified),
            owner=_decode_text(owner),
            group=_decode_text(group),
            permissions=_format_permissions(mode),
            path=_decode_text(path),
        ))
    return files


def _decode_text(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _parse_int(value: bytes) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _parse_timestamp(value: bytes) -> int:
    try:
        return int(float(value))
    except ValueError:
        return 0


def _format_permissions(value: bytes) -> str:
    try:
        mode = int(value, 8)
    except ValueError:
        return "0"
    return "0%o" % (mode & 0o777)


def _raise_exec_error(stderr: bytes, exit_code: int) -> None:
    message = stderr.decode("utf-8", errors="replace").strip()
    if "No such file or directory" in message:
        raise FileNotFoundError("path not found")
    if "already exists" in message:
        raise FileExistsError(message or "file already exists")
    raise RuntimeError(message or f"sandbox file operation failed (exit code {exit_code})")
