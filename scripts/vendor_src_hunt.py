"""把独立 src-hunt 方法论仓库生成到 ravenholt 的 strix 技能目录。

源：``e:/codex_work/开发/src-hunt``（SKILL.md + references/01..10 + references/知识库/*.md）
产物：``strix/skills/src_hunt/*.md``（扁平化 + frontmatter + ravenholt 环境改写）

环境改写规则全部在 ``src-hunt/profiles/ravenholt.yaml``，脚本本身不含业务文本。
这样可以做到：

* src-hunt 保持原样（WorkBuddy/环境无关），ravenholt 只生成自己的版本；
* 重新同步时执行一次即可，不会把旧环境路径带回来；
* ``--check`` 可在 CI 里校验产物与源+profile 一致。

用法（在 ravenholt 仓库根目录）：

    .venv\\Scripts\\python.exe scripts\\vendor_src_hunt.py
    .venv\\Scripts\\python.exe scripts\\vendor_src_hunt.py --check
    .venv\\Scripts\\python.exe scripts\\vendor_src_hunt.py --only SKILL.md,idor-test.md --out _dev\\sample

退出码：0 成功；1 校验失败 / 有禁用残留；2 参数或 IO 错误。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = REPO_ROOT / "strix" / "skills" / "src_hunt"
DEFAULT_MANIFEST = REPO_ROOT / ".src-hunt-vendor.json"
DEFAULT_PROFILE = Path("e:/codex_work/开发/src-hunt/profiles/ravenholt.yaml")

_FRONTMATTER = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


class VendorError(RuntimeError):
    """源、profile 或目标不可用。"""


def _read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VendorError(f"无法读取 {path}: {exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_profile(path: Path) -> dict[str, Any]:
    raw = _read_text(path)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise VendorError(f"profile YAML 解析失败: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise VendorError(f"profile 根节点必须是映射: {path}")
    return data


def _iter_sources(source_root: Path) -> list[tuple[str, Path]]:
    """返回 (产物文件名, 源文件) 列表，顺序稳定。"""
    entries: list[tuple[str, Path]] = []

    skill = source_root / "SKILL.md"
    if not skill.is_file():
        raise VendorError(f"缺少源文件: {skill}")
    entries.append(("SKILL.md", skill))

    references = source_root / "references"
    if not references.is_dir():
        raise VendorError(f"缺少 references 目录: {references}")
    for path in sorted(references.glob("[0-9][0-9]-*.md")):
        entries.append((path.name, path))

    knowledge = references / "知识库"
    if not knowledge.is_dir():
        raise VendorError(f"缺少知识库目录: {knowledge}")
    for path in sorted(knowledge.glob("*.md")):
        if path.name == "README.md":
            continue
        entries.append((path.name, path))

    names = [name for name, _ in entries]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise VendorError(f"产物文件名冲突: {duplicates}")
    return entries


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _description_for(
    name: str,
    body: str,
    profile: dict[str, Any],
) -> str:
    overrides = (profile.get("frontmatter") or {}).get("description_overrides") or {}
    value = str(overrides.get(name) or _first_heading(body) or name)
    value = " ".join(value.split())
    return value[:160]


def _ensure_frontmatter(name: str, body: str, profile: dict[str, Any]) -> str:
    settings = profile.get("frontmatter") or {}
    if not settings.get("enabled", True):
        return body
    if _FRONTMATTER.match(body):
        return body
    stem = Path(name).stem
    description = _description_for(name, body, profile)
    frontmatter = (
        "---\n"
        f"name: {json.dumps(stem, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
    )
    return frontmatter + body.lstrip("\n")


def _insert_note(body: str, note: str) -> str:
    if not note.strip():
        return body
    matched = _FRONTMATTER.match(body)
    if matched:
        head_end = matched.end()
        return body[:head_end] + note.strip() + "\n\n" + body[head_end:].lstrip("\n")
    return note.strip() + "\n\n" + body.lstrip("\n")


def _apply_sections(
    name: str,
    body: str,
    profile: dict[str, Any],
    profile_dir: Path,
) -> str:
    for rule in profile.get("section_replacements") or []:
        if str(rule.get("file")) != name:
            continue
        pattern = str(rule.get("pattern") or "")
        if not pattern:
            raise VendorError(f"{name}: section_replacements 缺少 pattern")
        replacement_file = rule.get("replacement_file")
        if replacement_file:
            replacement = _read_text(profile_dir / str(replacement_file))
        else:
            replacement = str(rule.get("replace") or "")
        new_body, count = re.subn(pattern, lambda _m: replacement, body, flags=re.MULTILINE | re.DOTALL)
        if count:
            body = new_body
    return body


def _apply_replacements(body: str, profile: dict[str, Any]) -> str:
    for rule in profile.get("replacements") or []:
        pattern = str(rule.get("pattern") or "")
        if not pattern:
            raise VendorError("replacements 规则缺少 pattern")
        replacement = str(rule.get("replace") or "")
        body = re.sub(pattern, replacement, body)
    return body


def _render(
    name: str,
    source_text: str,
    profile: dict[str, Any],
    profile_dir: Path,
) -> str:
    body = source_text
    body = _apply_sections(name, body, profile, profile_dir)
    body = _apply_replacements(body, profile)
    body = _ensure_frontmatter(name, body, profile)
    body = _insert_note(body, str(profile.get("per_file_note") or ""))
    if not body.endswith("\n"):
        body += "\n"
    return body


def _build(
    source_root: Path,
    profile: dict[str, Any],
    profile_path: Path,
    only: list[str],
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    profile_dir = profile_path.parent
    outputs: dict[str, str] = {}
    sources: dict[str, dict[str, str]] = {}
    for name, path in _iter_sources(source_root):
        if only and not any(token in name for token in only):
            continue
        raw = _read_text(path)
        outputs[name] = _render(name, raw, profile, profile_dir)
        sources[name] = {
            "source": str(path.relative_to(source_root)).replace("\\", "/"),
            "source_sha256": _sha256(raw),
        }
    return outputs, sources


def _forbidden_hits(outputs: dict[str, str], profile: dict[str, Any]) -> list[str]:
    tokens = [str(token) for token in profile.get("forbidden") or [] if str(token)]
    hits: list[str] = []
    for name, body in sorted(outputs.items()):
        for token in tokens:
            if token in body:
                line = next(
                    (i for i, text in enumerate(body.splitlines(), 1) if token in text),
                    None,
                )
                hits.append(f"{name}:{line}: 残留 {token!r}")
    return hits


def _write_outputs(
    outputs: dict[str, str],
    sources: dict[str, dict[str, str]],
    target: Path,
    manifest_path: Path,
    source_root: Path,
    profile_path: Path,
    profile: dict[str, Any],
    only: list[str],
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, body in outputs.items():
        (target / name).write_text(body, encoding="utf-8", newline="\n")
    if not only:
        expected = set(outputs)
        for path in target.glob("*.md"):
            if path.name not in expected:
                path.unlink()

    manifest = {
        "source_root": str(source_root),
        "profile": str(profile_path),
        "profile_version": profile.get("version"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vendor_file_count": len(outputs),
        "files": {
            name: {**sources[name], "output_sha256": _sha256(body)}
            for name, body in sorted(outputs.items())
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _check(
    outputs: dict[str, str],
    target: Path,
    profile: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    for name, body in sorted(outputs.items()):
        path = target / name
        if not path.is_file():
            problems.append(f"缺少产物: {name}")
        elif _read_text(path) != body:
            problems.append(f"内容不一致: {name}")
    expected = set(outputs)
    for path in sorted(target.glob("*.md")):
        if path.name not in expected:
            problems.append(f"多出产物: {path.name}")
    problems.extend(_forbidden_hits(outputs, profile))
    return problems


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=None, help="src-hunt 仓库根目录")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="环境 profile YAML")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="产物目录")
    parser.add_argument("--manifest", type=Path, default=None, help="产物清单路径")
    parser.add_argument("--only", default="", help="只处理文件名包含这些子串的条目（逗号分隔）")
    parser.add_argument("--out", type=Path, default=None, help="写到临时目录（样例模式）")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.profile.is_file():
        print(f"[error] profile 不存在: {args.profile}", file=sys.stderr)
        return 2
    profile = _load_profile(args.profile)
    source_root = args.source or Path(str(profile.get("source_root") or ""))
    if not source_root or not source_root.is_dir():
        print(f"[error] src-hunt 源目录不存在: {source_root}", file=sys.stderr)
        return 2

    only = [token.strip() for token in str(args.only).split(",") if token.strip()]
    target = args.out or args.target
    manifest = args.manifest or (
        target / ".src-hunt-vendor.json" if args.out else DEFAULT_MANIFEST
    )

    try:
        outputs, sources = _build(source_root, profile, args.profile, only)
    except VendorError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 2

    if args.check:
        problems = _check(outputs, target, profile)
        if problems:
            print(f"[FAIL] {len(problems)} 项不一致：")
            for item in problems[:80]:
                print(f"  - {item}")
            if len(problems) > 80:
                print(f"  ... 另有 {len(problems) - 80} 项")
            return 1
        print(f"[OK] {len(outputs)} 篇产物与 src-hunt + profile 一致，无禁用残留。")
        return 0

    try:
        _write_outputs(
            outputs,
            sources,
            target,
            manifest,
            source_root,
            args.profile,
            profile,
            only,
        )
    except OSError as exc:
        print(f"[error] 写入失败: {exc}", file=sys.stderr)
        return 2

    hits = _forbidden_hits(outputs, profile)
    print(f"[OK] 生成 {len(outputs)} 篇 → {target}")
    print(f"     manifest → {manifest}")
    if hits:
        print(f"[WARN] 仍有 {len(hits)} 处禁用残留（--check 会拒绝）：")
        for item in hits[:40]:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
