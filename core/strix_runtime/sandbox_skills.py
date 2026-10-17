"""把镜像内建的工具技能（``sandbox/.agents/skills``）接进 strix 的技能加载器。

背景：一体化沙箱镜像为定制工具链（ghidra / jadx / apktool / binwalk / observer_ward /
agent-browser-cli 等）随附了一批 ``<name>/SKILL.md`` 技能，但 strix 的技能加载器只搜索
包内 ``strix/skills`` 以及 ``register_skill_dir()`` 显式注册的目录，且期望的布局是
``<root>/<category>/<name>.md`` —— 与 ``<name>/SKILL.md`` 不兼容，于是这批技能实际上
从来没被 agent 读到（读它们的那套平台工具已随「单轨化到 strix」退役）。

这里在启动时做一次「扁平化 + 注册」：把 ``<name>/SKILL.md`` 转成 ``ravenholt/<name>.md``
放进工作区目录，再注册给 strix。技能正文里引用的资源路径（``.agents/skills/<name>/...``）
在沙箱容器内依旧有效，因此不需要改写文件内容。

与 strix 内置同名的技能（如 ``nmap`` / ``sqlmap`` / ``httpx``）会跳过 —— 内置版本更完整，
且同名会造成 ``_get_ambiguous_skill_names()`` 意义上的歧义（名字是裸名，不带类别前缀）。
"""

from __future__ import annotations

from pathlib import Path

from logger import get_logger


logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_SKILLS_DIR = _PROJECT_ROOT / "sandbox" / ".agents" / "skills"
_TARGET_SUBDIR = "ravenholt"
_TARGET_DIRNAME = "skills-extra"


def register_sandbox_skill_dirs(workspace: Path) -> int:
    """扁平化镜像内技能并注册给 strix；返回注册的技能数（失败只记日志）。"""
    if not _SOURCE_SKILLS_DIR.is_dir():
        logger.debug("sandbox skills dir not found: %s", _SOURCE_SKILLS_DIR)
        return 0

    try:
        from strix.skills import get_all_skill_names, register_skill_dir
    except Exception:
        logger.warning("strix skills loader unavailable; skip sandbox skill registration", exc_info=True)
        return 0

    builtin_names = get_all_skill_names()
    target_root = workspace / _TARGET_DIRNAME
    target_dir = target_root / _TARGET_SUBDIR

    written = 0
    skipped: list[str] = []
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for skill_file in sorted(_SOURCE_SKILLS_DIR.glob("*/SKILL.md")):
            name = skill_file.parent.name
            if name in builtin_names:
                skipped.append(name)
                continue
            (target_dir / f"{name}.md").write_text(
                skill_file.read_text(encoding="utf-8"), encoding="utf-8",
            )
            written += 1
    except Exception:
        logger.warning("failed to flatten sandbox skills into %s", target_dir, exc_info=True)
        return 0

    register_skill_dir(target_root)
    logger.info(
        "sandbox skills registered: %d (skipped %d duplicated with strix built-ins: %s)",
        written,
        len(skipped),
        ", ".join(skipped) or "-",
    )
    return written
