"""源码包上传：把 zip / tar 归档安全解压进工作区，供源码审计项目作为 binary 资产挂载。

限额与依赖目录排除对齐 strix 上游的源码打包策略
(``strix/interface/cloud/source_upload.py``)，但这里是**服务端接收**：只保留体积 / 条目
上限与依赖目录排除，不沿用其"打包上传到云端"的隐私扫描逻辑。

安全要点（解压是最容易被打穿的一环）：拒绝绝对路径、``..`` 穿越、驱动器前缀、
符号链接 / 硬链接 / 设备文件，并在写入前再次确认目标落在本次上传目录内。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from config import WORKSPACE
from logger import get_logger
from schema.work_project.source_uploads import WorkProjectSourceUploadSchema


logger = get_logger(__name__)

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 250 * 1024 * 1024
MAX_ENTRIES = 20_000

#: 依赖 / 构建产物目录：审计不需要，且体积巨大。
_EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "vendor", "venv", ".venv", "env",
    "__pycache__", ".tox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "coverage", "target", ".next", ".nuxt", ".gradle",
})

_ZIP_SUFFIXES = (".zip",)
_TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz")
_SLUG_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")

SOURCE_STORAGE_ROOT = WORKSPACE / "source_uploads"


class SourceUploadError(ValueError):
    """上传包不合法：体积超限、格式不支持、归档损坏或包含不安全条目。"""


#: 归档条目：(相对路径, 是否目录, 字节数)；相对路径为空串表示该条目不可安全落盘。
Entry = tuple[str, bool, int]


async def store_source_upload(
    filename: str,
    stream: BinaryIO,
) -> tuple[WorkProjectSourceUploadSchema | None, str]:
    """接收一个源码归档并解压；返回 (结果, 错误信息)，两者互斥。"""
    if _archive_suffix(filename) is None:
        return None, "unsupported source archive: expected .zip / .tar / .tar.gz / .tgz"
    try:
        schema = await asyncio.to_thread(_store_sync, filename, stream)
    except SourceUploadError as exc:
        return None, str(exc)
    except Exception:  # noqa: BLE001 - 归档损坏等一律收敛成可读错误
        logger.exception("source archive unpack failed")
        return None, "failed to unpack the source archive"
    return schema, ""


def stored_source_dir(path: str) -> Path | None:
    """路径若在平台源码上传区内，返回它所属的上传目录（token 目录）；否则返回 None。

    只认平台自己解压出来的目录（``WORKSPACE/source_uploads/<token>/…``）。用户手填的任意
    路径（例如自己的 ``/opt/source``）一律不认，清理时绝不碰。
    """
    try:
        resolved = Path(path).resolve()
        root = SOURCE_STORAGE_ROOT.resolve()
    except OSError:
        return None
    if resolved == root:
        return None
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return None
    token = relative.parts[0] if relative.parts else ""
    return root / token if token else None


async def purge_stored_sources(paths: list[str]) -> int:
    """删除这些路径所属的上传目录，返回真正删掉的目录数。

    项目删除时调用：一次上传对应一个 token 目录（``<slug>`` 就在其中），删掉整个 token 目录
    即删干净该项目的源码包。失败只记日志、不抛错 —— 项目已经删了，清理不该反过来阻塞请求。
    """
    targets = {target for target in (stored_source_dir(path) for path in paths) if target is not None}
    removed = 0
    for target in targets:
        try:
            if await asyncio.to_thread(target.is_dir):
                await asyncio.to_thread(shutil.rmtree, target, True)
                removed += 1
                logger.info("source upload purged: %s", target)
        except OSError:
            logger.warning("failed to purge source upload: %s", target, exc_info=True)
    return removed


def _archive_suffix(filename: str) -> str | None:
    lowered = (filename or "").strip().lower()
    for suffix in _TAR_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    for suffix in _ZIP_SUFFIXES:
        if lowered.endswith(suffix):
            return suffix
    return None


def _store_sync(filename: str, stream: BinaryIO) -> WorkProjectSourceUploadSchema:
    suffix = _archive_suffix(filename) or ".zip"
    SOURCE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    base = SOURCE_STORAGE_ROOT / token
    base.mkdir(parents=True)
    archive = base / f"upload{suffix}"
    try:
        _spill(stream, archive)
        entries = _list_entries(archive, suffix)
        slug = _slug_for(entries, filename)
        root = base / slug
        root.mkdir()
        file_count, total_bytes, skipped = _extract(archive, root, entries, suffix)
        archive.unlink()
        if file_count == 0:
            raise SourceUploadError("the archive contains no usable files")
    except Exception:
        shutil.rmtree(base, ignore_errors=True)
        raise
    logger.info(
        "source archive stored: token=%s slug=%s files=%s bytes=%s skipped=%s",
        token, slug, file_count, total_bytes, skipped,
    )
    return WorkProjectSourceUploadSchema(
        token=token,
        slug=slug,
        server_path=root.as_posix(),
        file_count=file_count,
        total_bytes=total_bytes,
        skipped_entries=skipped,
    )


def _spill(stream: BinaryIO, destination: Path) -> None:
    """把上传流落到磁盘，边写边卡总量上限，避免超大包吃满内存 / 磁盘。"""
    written = 0
    with destination.open("wb") as handle:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_ARCHIVE_BYTES:
                raise SourceUploadError(
                    f"archive exceeds the {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit"
                )
            handle.write(chunk)
    if written == 0:
        raise SourceUploadError("uploaded archive is empty")


def _list_entries(archive: Path, suffix: str) -> list[Entry]:
    """列出归档条目并按体积 / 条目数卡上限。"""
    entries: list[Entry] = []
    if suffix in _ZIP_SUFFIXES:
        try:
            with zipfile.ZipFile(archive) as handle:
                for info in handle.infolist():
                    if _is_zip_symlink(info):
                        entries.append((_safe_rel(info.filename) or "", False, 0))
                        continue
                    entries.append((_safe_rel(info.filename) or "", info.is_dir(), info.file_size))
        except zipfile.BadZipFile as exc:
            raise SourceUploadError("the uploaded file is not a valid zip archive") from exc
    else:
        try:
            with tarfile.open(archive, "r:*") as handle:
                for member in handle.getmembers():
                    if not (member.isfile() or member.isdir()):
                        entries.append((_safe_rel(member.name) or "", False, 0))
                        continue
                    entries.append((_safe_rel(member.name) or "", member.isdir(), member.size))
        except tarfile.TarError as exc:
            raise SourceUploadError("the uploaded file is not a valid tar archive") from exc

    if len(entries) > MAX_ENTRIES:
        raise SourceUploadError(f"archive has too many entries (limit {MAX_ENTRIES})")
    files = [entry for entry in entries if not entry[1]]
    if any(size > MAX_FILE_BYTES for _, _, size in files):
        raise SourceUploadError(
            f"a single file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit"
        )
    if sum(size for _, _, size in files) > MAX_TOTAL_BYTES:
        raise SourceUploadError(
            f"archive unpacks to more than {MAX_TOTAL_BYTES // (1024 * 1024)} MB"
        )
    return entries


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    """zip 里的符号链接靠外部属性中的 unix mode 标记（S_IFLNK）。"""
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def _safe_rel(name: str) -> str | None:
    """归一化成安全的相对路径；绝对路径、``..`` 穿越或控制字符返回 None。"""
    cleaned = (name or "").replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        return None
    parts: list[str] = []
    for part in cleaned.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or any(ord(char) < 0x20 or ord(char) == 0x7F for char in part):
            return None
        parts.append(part)
    return "/".join(parts) or None


def _strip_top(entries: list[Entry]) -> bool:
    """归档是否只有一个顶层目录（是则剥掉它，把内容直接放在 slug 下）。"""
    rels = [rel for rel, _, _ in entries if rel]
    if not rels or not any("/" in rel for rel in rels):
        return False
    return len({rel.split("/")[0] for rel in rels}) == 1


def _slug_for(entries: list[Entry], filename: str) -> str:
    """顶层目录名：归档若只有一个顶层目录就用它，否则用包名兜底。"""
    rels = [rel for rel, _, _ in entries if rel]
    tops = {rel.split("/")[0] for rel in rels}
    candidate = next(iter(tops)) if len(tops) == 1 and any("/" in rel for rel in rels) else _pack_name(filename)
    slug = _SLUG_ALLOWED.sub("-", candidate).strip(".-")
    return slug[:64] or "source"


def _pack_name(filename: str) -> str:
    """从上传文件名推断包名（``demo.tar.gz`` → ``demo``）。"""
    bare = Path((filename or "").strip()).name
    suffix = _archive_suffix(bare)
    if suffix:
        bare = bare[: len(bare) - len(suffix)]
    return bare or "upload"


def _extract(archive: Path, root: Path, entries: list[Entry], suffix: str) -> tuple[int, int, int]:
    """把归档写入 ``root``：剥离公共顶层目录，跳过依赖目录与不安全条目。

    目录项一律忽略（文件写入时按需建父目录，空目录对审计无价值）；符号链接、硬链接、
    设备文件与穿越路径计入 ``skipped``。
    """
    strip_top = _strip_top(entries)
    file_count = 0
    total_bytes = 0
    skipped = 0
    if suffix in _ZIP_SUFFIXES:
        with zipfile.ZipFile(archive) as handle:
            for info in handle.infolist():
                if info.is_dir():
                    continue
                rel = _file_rel(info.filename, _is_zip_symlink(info), strip_top)
                if rel is None:
                    skipped += 1
                    continue
                target = _resolve_within(root, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                with handle.open(info) as source, target.open("wb") as sink:
                    total_bytes += _copy_limited(source, sink)
                file_count += 1
        return file_count, total_bytes, skipped

    with tarfile.open(archive, "r:*") as handle:
        for member in handle.getmembers():
            if member.isdir():
                continue
            rel = _file_rel(member.name, not member.isfile(), strip_top)
            if rel is None:
                skipped += 1
                continue
            extracted = handle.extractfile(member)
            if extracted is None:
                skipped += 1
                continue
            target = _resolve_within(root, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            with extracted, target.open("wb") as sink:
                total_bytes += _copy_limited(extracted, sink)
            file_count += 1
    return file_count, total_bytes, skipped


def _file_rel(name: str, is_link: bool, strip_top: bool) -> str | None:
    """文件条目 → 落盘相对路径；不安全、符号链接、依赖目录与顶层目录项返回 None。"""
    if is_link:
        return None
    rel = _safe_rel(name)
    if rel is None:
        return None
    if strip_top:
        _, _, rel = rel.partition("/")
        if not rel:
            return None
    if any(part in _EXCLUDED_DIR_NAMES for part in rel.split("/")[:-1]):
        return None
    return rel


def _resolve_within(root: Path, rel: str) -> Path:
    """落到 ``root`` 之内；越界即抛错（二次防线，`_safe_rel` 已挡掉 `..`）。"""
    target = (root / rel).resolve()
    base = root.resolve()
    if target != base and base not in target.parents:
        raise SourceUploadError(f"archive entry escapes the upload directory: {rel}")
    return target


def _copy_limited(source: BinaryIO, sink: BinaryIO) -> int:
    """单文件流式复制，卡单文件体积上限（防解压炸弹式的单文件膨胀）。"""
    written = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            break
        written += len(chunk)
        if written > MAX_FILE_BYTES:
            raise SourceUploadError(
                f"a single file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit"
            )
        sink.write(chunk)
    return written
