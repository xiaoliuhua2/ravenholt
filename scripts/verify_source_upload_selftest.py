"""Self-test for the source-archive uploader (offline; no backend needed).

    python scripts/verify_source_upload_selftest.py            # Windows
    .venv/bin/python scripts/verify_source_upload_selftest.py  # POSIX

Covers the happy path (zip / tar with a single top-level directory stripped,
single-file archives, slug naming) and the safety rails: path traversal,
absolute paths, symlinks, dependency directories, per-file size limit,
unsupported / empty / corrupted archives.

Exit code is non-zero if any expectation fails.
"""

from __future__ import annotations

import asyncio
import io
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from service.work_project import source_uploads as uploads  # noqa: E402


CHECKS: list[tuple[str, bool]] = []


def _check(name: str, ok: bool) -> None:
    CHECKS.append((name, ok))
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}")


def _zip_bytes(entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as handle:
        for name, payload in entries.items():
            handle.writestr(name, payload)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o120777 << 16  # S_IFLNK
            handle.writestr(info, target)
    return buffer.getvalue()


def _tar_bytes(entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as handle:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))
        for name, target in (symlinks or {}).items():
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            handle.addfile(info)
    return buffer.getvalue()


async def _upload(filename: str, payload: bytes):
    return await uploads.store_source_upload(filename, io.BytesIO(payload))


async def main() -> int:
    original_root = uploads.SOURCE_STORAGE_ROOT
    original_file_limit = uploads.MAX_FILE_BYTES
    workdir = Path(tempfile.mkdtemp(prefix="rh-source-upload-"))
    uploads.SOURCE_STORAGE_ROOT = workdir / "source_uploads"
    try:
        # 1) 正常 zip：单一顶层目录被剥离
        schema, error = await _upload("demo.zip", _zip_bytes({
            "demo/app.py": b"print(1)\n",
            "demo/README.md": b"# demo\n",
        }))
        _check("1a 正常 zip 解压成功", schema is not None and error == "")
        if schema is not None:
            root = Path(schema.server_path)
            _check("1b slug 取顶层目录名", schema.slug == "demo")
            _check("1c 顶层目录被剥离", (root / "app.py").exists() and (root / "README.md").exists())
            _check("1d 文件内容正确", (root / "app.py").read_bytes() == b"print(1)\n")
            _check("1e 文件计数为 2", schema.file_count == 2)

        # 2) 单文件归档：不剥离顶层，slug 用包名
        schema2, _ = await _upload("single.zip", _zip_bytes({"main.py": b"x=1\n"}))
        _check(
            "2a 单文件归档不剥离且 slug 用包名",
            schema2 is not None and schema2.slug == "single"
            and (Path(schema2.server_path) / "main.py").exists(),
        )

        # 3) 目录穿越：条目被跳过，不写到上传目录之外
        schema3, _ = await _upload("evil.zip", _zip_bytes({
            "demo/ok.txt": b"ok",
            "demo/../escape.txt": b"pwn",
            "../outside.txt": b"pwn",
        }))
        _check("3a 穿越条目被跳过", schema3 is not None and schema3.skipped_entries >= 1)
        _check("3b 正常文件仍解出", schema3 is not None and schema3.file_count == 1)
        _check(
            "3c 未写到上传目录之外",
            not (workdir / "outside.txt").exists()
            and not (uploads.SOURCE_STORAGE_ROOT / "outside.txt").exists(),
        )

        # 4) 绝对路径条目被跳过
        schema4, _ = await _upload("abs.zip", _zip_bytes({
            "/etc/passwd": b"root:x:0:0",
            "demo/a.txt": b"a",
        }))
        _check("4a 绝对路径条目被跳过", schema4 is not None and schema4.file_count == 1)

        # 5) zip 软链接被跳过
        schema5, _ = await _upload("link.zip", _zip_bytes(
            {"demo/a.txt": b"a"}, {"demo/link": "/etc/passwd"},
        ))
        _check("5a zip 软链接被跳过", schema5 is not None and schema5.file_count == 1 and schema5.skipped_entries == 1)
        _check("5b zip 软链接未落盘", schema5 is not None and not (Path(schema5.server_path) / "link").exists())

        # 6) tar 软链接被跳过
        schema6, _ = await _upload("link.tar.gz", _tar_bytes(
            {"demo/a.txt": b"a"}, {"demo/link": "/etc/passwd"},
        ))
        _check("6a tar 软链接被跳过", schema6 is not None and schema6.file_count == 1)
        _check("6b tar 软链接未落盘", schema6 is not None and not (Path(schema6.server_path) / "link").exists())

        # 7) 依赖 / 构建目录被排除
        schema7, _ = await _upload("deps.zip", _zip_bytes({
            "demo/a.txt": b"a",
            "demo/node_modules/x.js": b"x",
            "demo/.git/config": b"c",
        }))
        _check("7a 依赖目录被排除", schema7 is not None and schema7.file_count == 1 and schema7.skipped_entries == 2)

        # 8) 正常 tar：多级目录
        schema8, _ = await _upload("demo.tar.gz", _tar_bytes({
            "demo/a.txt": b"a",
            "demo/sub/b.txt": b"b",
        }))
        _check(
            "8a tar 解压并保留子目录",
            schema8 is not None and (Path(schema8.server_path) / "sub" / "b.txt").read_bytes() == b"b",
        )

        # 9) 单文件体积上限（把上限压小，避免真的造 25MB 包）
        uploads.MAX_FILE_BYTES = 8
        schema9, error9 = await _upload("big.zip", _zip_bytes({"demo/big.bin": b"0123456789abcdef"}))
        _check("9a 超单文件上限被拒", schema9 is None and "single file" in error9)
        uploads.MAX_FILE_BYTES = original_file_limit

        # 10) 不支持的扩展名
        schema10, error10 = await _upload("notes.txt", b"hello")
        _check("10a 不支持的扩展名被拒", schema10 is None and "unsupported" in error10)

        # 11) 空归档（只有目录项）
        schema11, error11 = await _upload("empty.zip", _zip_bytes({"demo/": b""}))
        _check("11a 无可用文件被拒", schema11 is None and "no usable files" in error11)

        # 12) 损坏归档
        schema12, _ = await _upload("broken.zip", b"PK\x03\x04not-really-a-zip")
        _check("12a 损坏归档被拒", schema12 is None)

        # 13) 所有落盘目录都在存储根下
        storage_root = uploads.SOURCE_STORAGE_ROOT
        dirs = [child for child in storage_root.iterdir() if child.is_dir()]
        _check(
            "13a 上传目录都在存储根下",
            bool(dirs) and all(child.parent == storage_root for child in dirs),
        )
    finally:
        uploads.SOURCE_STORAGE_ROOT = original_root
        uploads.MAX_FILE_BYTES = original_file_limit
        shutil.rmtree(workdir, ignore_errors=True)

    failed = [name for name, ok in CHECKS if not ok]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} 项通过")
    if failed:
        print("失败项：" + " / ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
