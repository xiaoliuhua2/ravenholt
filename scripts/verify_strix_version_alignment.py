"""vendored strix 代码 ↔ 沙箱镜像 版本对齐校验（feature ⑦）。

背景：``ravenholt/strix`` 是从 ``usestrix/strix`` 原样 vendored 的代码，而沙箱容器实际
运行的镜像 tag 是**独立演进**的（ravenholt 侧由 ``sandbox_images`` 表里的 ``image_name``
决定；strix 侧有 ``STRIX_IMAGE`` 默认值）。代码升级了但镜像没升（或反之）会造成提示词 /
工具面与镜像内工具链不一致，这里把这种漂移显式暴露出来。

用法（仓库根，离线可跑；DB 不可用时自动跳过该项）：

    .venv/bin/python scripts/verify_strix_version_alignment.py

判定：
  * vendored 文件树与 ``.strix-vendor.json`` 基线不一致 → FAIL（代码被本地改过 / 清单过期）；
  * 镜像引用不一致 → WARN（可能是刻意为之，需人工确认）；
  * 其余 PASS。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _path in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from sync_strix import DEFAULT_UPSTREAM_CLONE, scan  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / ".strix-vendor.json"
DEFAULT_VENDOR = REPO_ROOT / "strix"

results: list[tuple[str, str]] = []  # (level, message)


def _record(level: str, message: str) -> None:
    results.append((level, message))
    print(f"  [{level}] {message}")


def _read_manifest(path: Path) -> dict | None:
    if not path.is_file():
        _record("FAIL", f"缺少来源清单 {path}；先执行 scripts/sync_strix.py --apply")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _record("FAIL", f"来源清单不可解析：{path}（{exc}）")
        return None


def _upstream_version(upstream: Path) -> str:
    pyproject = upstream / "pyproject.toml"
    if not pyproject.is_file():
        return ""
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def _tree_drift(manifest: dict, vendor: Path) -> list[str]:
    baseline: dict[str, str] = manifest.get("vendor_files") or {}
    current = scan(vendor)
    drift = sorted(
        {f"+ 新增 {rel}" for rel in set(current) - set(baseline)}
        | {f"- 缺失 {rel}" for rel in set(baseline) - set(current)}
        | {f"~ 改动 {rel}" for rel in set(current) & set(baseline) if current[rel] != baseline[rel]}
    )
    return drift


async def _db_image_names() -> list[str] | None:
    """ravenholt 侧实际使用的沙箱镜像（platform 走 DB 记录，不读 STRIX_IMAGE）。"""
    try:
        from sqlmodel import select

        from config import load_config
        from database import get_async_session, init_engine
        from model.sandbox.images import SandboxImage

        load_config()
        init_engine()
        async with get_async_session() as session:
            rows = (await session.exec(select(SandboxImage))).all()
        return sorted({str(row.image_name) for row in rows if row.image_name})
    except Exception as exc:  # noqa: BLE001 - DB 不可用时该项跳过，不影响其余校验
        print(f"  [skip] 沙箱镜像表不可读（DB 未启动或未配置）：{exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 vendored strix 与沙箱镜像的版本对齐")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--vendor", type=Path, default=DEFAULT_VENDOR)
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM_CLONE)
    args = parser.parse_args(argv)

    print("=" * 64)
    print("vendored strix 代码 ↔ 沙箱镜像 对齐校验")
    print("=" * 64)

    manifest = _read_manifest(args.manifest)
    if manifest is None:
        return 1

    print("  上游来源：{} @ {}（{}），同步于 {}".format(
        manifest.get("upstream_remote") or "<未知>",
        (manifest.get("upstream_commit") or "?")[:12],
        manifest.get("upstream_described") or "-",
        manifest.get("synced_at") or "-",
    ))
    version = _upstream_version(args.upstream)
    print(f"  上游代码版本：{version or '<上游克隆不可用，跳过>'}")

    # 1) vendored 文件树完整性
    drift = _tree_drift(manifest, args.vendor)
    if drift:
        _record("FAIL", f"vendored 与基线不一致（{len(drift)} 个文件；前 10 条）")
        for item in drift[:10]:
            print(f"        {item}")
        if len(drift) > 10:
            print(f"        ... 其余 {len(drift) - 10} 条省略")
    else:
        _record("PASS", f"vendored 文件树与基线一致（{len(manifest.get('vendor_files') or {})} 个文件）")

    # 2) 镜像引用对齐
    baseline_images = sorted(manifest.get("sandbox_images") or [])
    live_images: dict[str, str] = {}
    env_image = os.environ.get("STRIX_IMAGE", "").strip()
    if env_image:
        live_images["环境变量 STRIX_IMAGE"] = env_image
    settings = args.vendor / "config" / "settings.py"
    if settings.is_file():
        found = re.findall(r"[\w./@-]*strix-sandbox:[\w.-]+", settings.read_text("utf-8"))
        for ref in sorted(set(found)):
            live_images["vendored settings 默认值"] = ref
    db_images = asyncio.run(_db_image_names())
    if db_images is not None:
        for ref in db_images:
            live_images[f"平台沙箱镜像表（{ref}）"] = ref

    print(f"  清单记录镜像：{baseline_images or '<无>'}")
    for label, ref in live_images.items():
        print(f"  现场镜像    ：{label} -> {ref}")

    mismatched = sorted({ref for ref in live_images.values() if ref not in baseline_images})
    if not baseline_images:
        _record("WARN", "清单未记录沙箱镜像；请重跑 sync_strix.py --apply 以建立基线")
    elif mismatched:
        _record("WARN", f"现场镜像与清单基线不一致：{mismatched}（人工确认是否有意为之）")
    else:
        _record("PASS", "现场沙箱镜像与清单基线一致")

    failed = [msg for level, msg in results if level == "FAIL"]
    warned = [msg for level, msg in results if level == "WARN"]
    print("-" * 64)
    print(f"对齐校验 -> {'FAIL' if failed else 'PASS'}"
          f"（FAIL {len(failed)} / WARN {len(warned)}）")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
