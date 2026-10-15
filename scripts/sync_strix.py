"""strix 上游同步（vendored 原样 + 仅 src_hunt 增量）。

用法（在仓库根执行）：

    .venv/bin/python scripts/sync_strix.py                 # 差异预览（不写盘）
    .venv/bin/python scripts/sync_strix.py --apply         # 确认后覆盖
    .venv/bin/python scripts/sync_strix.py --apply --prune # 并删除上游已移除的文件

约定（与项目既定的 vendored 策略一致）：
  * ``ravenholt/strix`` 是上游 ``usestrix/strix`` 的包目录，**原样 vendored**，不做裁剪；
  * ravenholt 自己的增量只放在 ``strix/skills/src_hunt/``（skill 加载器按目录扫描，天然隔离）；
  * 因此默认**只新增/覆盖**，不删除；``--prune`` 也会显式跳过 ``skills/src_hunt/**``；
  * 每次 ``--apply`` 会把上游来源（remote / commit / 描述）与文件哈希写入
    ``.strix-vendor.json``，用于日后核对「vendored 是否被本地改过」。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM_CLONE = REPO_ROOT.parent / "strix"
DEFAULT_VENDOR = REPO_ROOT / "strix"
DEFAULT_MANIFEST = REPO_ROOT / ".strix-vendor.json"

# ravenholt 自有增量目录：同步绝不删除、绝不覆盖
PROTECTED_PREFIX = "skills/src_hunt/"
SKIP_DIR_NAMES = {".git", ".github", "node_modules", "__pycache__", ".venv", ".mypy_cache",
                  ".ruff_cache", ".pytest_cache", "dist", "build"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan(root: Path) -> dict[str, str]:
    """相对路径 -> sha256；跳过缓存/构建产物。"""
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.name.endswith(SKIP_SUFFIXES):
            continue
        rel = path.relative_to(root).as_posix()
        files[rel] = _hash_file(path)
    return files


def resolve_upstream(path: Path) -> tuple[Path, Path | None]:
    """接受「克隆根」或「包目录」，返回 (包目录, 克隆根或 None)。"""
    candidate = path / "strix"
    if (candidate / "__init__.py").exists():
        return candidate, path
    if path.name == "strix" and (path / "__init__.py").exists():
        parent = path.parent
        return path, parent if (parent / ".git").exists() else None
    raise SystemExit(
        f"无法定位上游 strix 包：{path}\n"
        f"  期望指向克隆根（含 strix/__init__.py）或包目录本身。"
    )


IMAGE_REF_RE = re.compile(r"[\w./@-]*strix-sandbox:[\w.-]+")


def read_sandbox_images(pkg: Path) -> list[str]:
    """从 vendored settings 里抽出现场使用的沙箱镜像引用（代码 ↔ 镜像对齐用）。"""
    settings = pkg / "config" / "settings.py"
    if not settings.exists():
        return []
    return sorted({match.group(0) for match in IMAGE_REF_RE.finditer(settings.read_text("utf-8"))})


def _git(repo: Path | None, *args: str) -> str:
    if repo is None:
        return ""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def diff(upstream: dict[str, str], vendor: dict[str, str]) -> dict[str, list[str]]:
    only_upstream = sorted(set(upstream) - set(vendor))
    only_vendor = sorted(set(vendor) - set(upstream))
    changed = sorted(k for k in set(upstream) & set(vendor) if upstream[k] != vendor[k])
    return {"only_upstream": only_upstream, "only_vendor": only_vendor, "changed": changed}


def _report(result: dict[str, list[str]], limit: int) -> None:
    for header, key in (
        ("上游有、vendored 没有（将新增）", "only_upstream"),
        ("vendored 有、上游没有（默认保留）", "only_vendor"),
        ("两边都有但内容不同（将覆盖）", "changed"),
    ):
        items = result[key]
        print(f"\n-- {header}：{len(items)} --")
        for rel in items[:limit]:
            print("   ", rel)
        if len(items) > limit:
            print(f"    ... 其余 {len(items) - limit} 条省略")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步 vendored strix（预览 → 确认 → 覆盖）")
    parser.add_argument("--upstream", type=Path, default=DEFAULT_UPSTREAM_CLONE,
                        help="上游克隆根或 strix 包目录")
    parser.add_argument("--vendor", type=Path, default=DEFAULT_VENDOR, help="vendored 包目录")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="来源清单路径")
    parser.add_argument("--apply", action="store_true", help="真正写盘（缺省仅预览）")
    parser.add_argument("--prune", action="store_true",
                        help="同时删除上游已移除的文件（永不删 skills/src_hunt/**）")
    parser.add_argument("--limit", type=int, default=50, help="每类差异最多打印多少条")
    args = parser.parse_args(argv)

    upstream_pkg, repo_root = resolve_upstream(args.upstream)
    vendor_pkg = args.vendor
    if not (vendor_pkg / "__init__.py").exists():
        print(f"!! vendored 包目录不可用：{vendor_pkg}", file=sys.stderr)
        return 2

    upstream_files = scan(upstream_pkg)
    vendor_files = scan(vendor_pkg)
    result = diff(upstream_files, vendor_files)

    remote = _git(repo_root, "remote", "get-url", "origin")
    commit = _git(repo_root, "rev-parse", "HEAD")
    described = _git(repo_root, "describe", "--tags", "--always")
    branch = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")

    print("=" * 64)
    print("strix 同步差异预览")
    print(f"  上游包  ：{upstream_pkg}")
    print(f"  来源    ：{remote or '<非 git 目录>'} @ {commit[:12] or '?'} ({described or '-'})")
    print(f"  vendored：{vendor_pkg}")
    print(f"  文件数  ：上游 {len(upstream_files)} | vendored {len(vendor_files)}")
    print(f"  沙箱镜像：{read_sandbox_images(vendor_pkg) or '<未发现>'}")
    print("=" * 64)
    _report(result, args.limit)

    protected_hits = [rel for rel in result["only_vendor"] if rel.startswith(PROTECTED_PREFIX)]
    print(f"\n-- ravenholt 增量（受保护，始终保留）：{len(protected_hits)} 个 src_hunt 文件 --")

    deletions = [rel for rel in result["only_vendor"] if not rel.startswith(PROTECTED_PREFIX)]
    to_copy = result["only_upstream"] + result["changed"]

    if not args.apply:
        print("\n预览模式：未修改任何文件。加 --apply 覆盖 "
              f"{len(to_copy)} 个文件"
              + (f"，并删除 {len(deletions)} 个上游已移除文件（--prune）" if args.prune else "")
              + "。")
        return 0

    copied = 0
    for rel in to_copy:
        src = upstream_pkg / rel
        dst = vendor_pkg / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    removed = 0
    if args.prune:
        for rel in deletions:
            target = vendor_pkg / rel
            if target.exists():
                target.unlink()
                removed += 1
        # 清理可能变空的目录（不碰受保护前缀）
        for path in sorted(vendor_pkg.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()) and not any(
                part in {"skills"} for part in path.relative_to(vendor_pkg).parts
            ):
                path.rmdir()

    final_vendor = scan(vendor_pkg)
    manifest = {
        "upstream_remote": remote,
        "upstream_commit": commit,
        "upstream_described": described,
        "upstream_branch": branch,
        "upstream_path": str(upstream_pkg),
        "vendor_path": str(vendor_pkg),
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synced_files": {"copied": copied, "removed": removed},
        "protected_prefix": PROTECTED_PREFIX,
        "sandbox_images": read_sandbox_images(vendor_pkg),
        "vendor_file_count": len(final_vendor),
        "vendor_files": final_vendor,
    }
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n已覆盖 {copied} 个文件"
          + (f"，删除 {removed} 个" if args.prune else "")
          + f"；来源清单已写入 {args.manifest}")
    residual = diff(upstream_files, final_vendor)
    drift = [rel for rel in residual["changed"]]
    print(f"校验：与上游仍不同 {len(drift)} 个文件"
          f"{'，仅 src_hunt 增量：' + str(len(residual['only_vendor'])) + ' 个' if residual['only_vendor'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
