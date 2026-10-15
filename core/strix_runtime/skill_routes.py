"""确定性技能路由：把「现场指纹 / 特征」映射到一组确定的 src_hunt 技能。

目的：减少 agent 随机 ``load_skill``。映射表是**数据**，不是代码：

- 工厂默认：``core/strix_runtime/skill_routes.default.yaml``（随仓库提交）
- 实例覆盖：``.ravenholt/skill_routes.yaml``（存在即整体覆盖默认，该文件不提交）

加载语义是 **best-effort**（与红线策略的 fail-closed 不同）：路由表不是安全网，
缺失/损坏时退回工厂默认并打告警，绝不影响平台启动。

agent 侧入口是 ``route_skills`` 工具（见 ``SKILL_ROUTE_TOOLS``）；匹配按小写子串命中，
返回限定名 ``src_hunt/<技能>``，与 strix 加载器的 ``<category>/<name>`` 形式一致。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from agents import RunContextWrapper, function_tool
from pydantic import ValidationError

from config import WORKSPACE
from core.strix_runtime.prompts import RuntimeMode
from logger import get_logger
from schema.agent.skill_routes import SkillRoute, SkillRoutesConfig


logger = get_logger(__name__)

DEFAULT_ROUTES_FILE = Path(__file__).resolve().parent / "skill_routes.default.yaml"
INSTANCE_ROUTES_FILE = WORKSPACE / "skill_routes.yaml"

_lock = threading.RLock()
_cache: SkillRoutesConfig | None = None
_cache_source: Path | None = None


class SkillRoutesError(RuntimeError):
    """显式指定的路由表不可用（仅显式加载时抛出）。"""


def instance_routes_path() -> Path:
    """实例覆盖文件的路径（可能不存在）。"""
    return INSTANCE_ROUTES_FILE


def _load_raw(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SkillRoutesError(f"技能路由表不可读：{path}（{exc}）") from exc
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise SkillRoutesError(f"技能路由表 YAML 解析失败：{path}（{exc}）") from exc
    if not isinstance(data, dict):
        raise SkillRoutesError(f"技能路由表根节点必须是映射：{path}")
    return data


def _validate(data: dict[str, Any], path: Path) -> SkillRoutesConfig:
    try:
        return SkillRoutesConfig.model_validate(data)
    except ValidationError as exc:
        raise SkillRoutesError(f"技能路由表校验失败：{path}\n{exc}") from exc


def load_skill_routes(path: Path | None = None) -> SkillRoutesConfig:
    """显式加载指定路由表；失败即抛错（供脚本 / 测试使用）。"""
    target = path or DEFAULT_ROUTES_FILE
    return _validate(_load_raw(target), target)


def merge_routes(
    base: SkillRoutesConfig,
    base_raw: dict[str, Any],
    override: SkillRoutesConfig,
    override_raw: dict[str, Any],
) -> SkillRoutesConfig:
    """实例覆盖表按 id 合并进工厂默认（只增强、不限制）。

    - 与默认同 ``id`` 的实例条目**替换**默认条目；
    - ``disabled_routes`` 里的 id 从默认里**移除**；
    - ``max_skills`` / ``fallback_skills`` / ``version`` 仅在实例文件**显式写出**时覆盖。
    """
    disabled = set(override.disabled_routes)
    override_ids = {route.id for route in override.routes}
    routes = [
        route for route in base.routes if route.id not in disabled and route.id not in override_ids
    ] + list(override.routes)

    data = base.model_dump()
    data["routes"] = [route.model_dump() for route in routes]
    for key in ("version", "max_skills", "fallback_skills"):
        if key in override_raw:
            data[key] = getattr(override, key)
    return SkillRoutesConfig.model_validate(data)


def _known_skill_names() -> set[str]:
    """strix 加载器当前可解析的全部技能名（裸名 + 限定名）。"""
    try:
        from strix.skills import _get_all_skill_keys, get_all_skill_names  # noqa: PLC0415

        return set(get_all_skill_names()) | set(_get_all_skill_keys())
    except Exception:  # noqa: BLE001 - 技能目录不可用时不影响路由可用性
        logger.warning("无法枚举 strix 技能名，跳过技能存在性校验")
        return set()


def unknown_skills(config: SkillRoutesConfig, known: set[str] | None = None) -> list[str]:
    """路由表里引用了但加载器解析不到的技能名（去重排序）。"""
    available = _known_skill_names() if known is None else known
    if not available:
        return []
    referenced = {skill for route in config.routes for skill in route.skills}
    referenced |= set(config.fallback_skills)
    return sorted(name for name in referenced if name not in available)


def get_skill_routes() -> SkillRoutesConfig:
    """取当前生效路由表（实例覆盖优先，失败退回工厂默认并告警）。"""
    global _cache, _cache_source
    with _lock:
        if _cache is not None:
            return _cache

        base_raw = _load_raw(DEFAULT_ROUTES_FILE)
        base = _validate(base_raw, DEFAULT_ROUTES_FILE)

        instance = instance_routes_path()
        if instance.is_file():
            try:
                override_raw = _load_raw(instance)
                override = _validate(override_raw, instance)
                _cache = merge_routes(base, base_raw, override, override_raw)
                _cache_source = instance
                logger.info(
                    "技能路由表已加载（工厂默认 + 实例覆盖 %s）：共 %d 条",
                    instance,
                    len(_cache.routes),
                )
            except SkillRoutesError as exc:
                logger.error("实例技能路由表不可用，退回工厂默认：%s", exc)
        if _cache is None:
            _cache = base
            _cache_source = DEFAULT_ROUTES_FILE
            logger.info(
                "技能路由表已加载（工厂默认）：%s（%d 条）", DEFAULT_ROUTES_FILE, len(_cache.routes)
            )

        missing = unknown_skills(_cache)
        if missing:
            logger.warning("技能路由表引用了未知技能（将被忽略）：%s", missing)
        return _cache


def reload_skill_routes() -> SkillRoutesConfig:
    """清缓存后重新加载（改过路由表 / 覆盖文件后调用）。"""
    global _cache, _cache_source
    with _lock:
        _cache, _cache_source = None, None
    return get_skill_routes()


def routes_source() -> Path | None:
    """当前路由表来源文件（未加载时为 None）。"""
    with _lock:
        return _cache_source


@dataclass(frozen=True)
class RouteMatch:
    route_id: str
    note: str
    hits: tuple[str, ...]
    skills: tuple[str, ...]


@dataclass(frozen=True)
class SkillRouteResult:
    observed: str
    matches: tuple[RouteMatch, ...]
    skills: tuple[str, ...]
    used_fallback: bool


def match_skills(
    observed: str,
    config: SkillRoutesConfig | None = None,
    *,
    known: set[str] | None = None,
    mode: RuntimeMode = RuntimeMode.PENETRATION,
) -> SkillRouteResult:
    """按现场观察文本做确定性路由。

    命中规则：``signals`` 中任一子串（小写）出现在 ``observed`` 里即算该条命中；
    按命中信号数降序（同分保持表内顺序）收集技能，去重后截到 ``max_skills``。
    一条都没命中 → 返回兜底技能：白盒（源码审计）会话优先用 ``audit_fallback_skills``。
    """
    cfg = config if config is not None else get_skill_routes()
    text = (observed or "").lower()

    available = known
    if available is None:
        available = _known_skill_names()

    def keep(names: list[str]) -> list[str]:
        if not available:
            return list(names)
        return [name for name in names if name in available]

    scored: list[tuple[int, int, SkillRoute, list[str]]] = []
    for index, route in enumerate(cfg.routes):
        hits = [signal for signal in route.signals if signal and signal.lower() in text]
        if hits:
            scored.append((len(hits), index, route, hits))
    scored.sort(key=lambda item: (-item[0], item[1]))

    skills: list[str] = []
    matches: list[RouteMatch] = []
    for _score, _index, route, hits in scored:
        route_skills = keep(route.skills)
        matches.append(RouteMatch(route.id, route.note, tuple(hits), tuple(route_skills)))
        for name in route_skills:
            if name not in skills:
                skills.append(name)

    used_fallback = not matches
    if used_fallback:
        fallback = cfg.fallback_skills
        if mode == RuntimeMode.SOURCE_AUDIT and cfg.audit_fallback_skills:
            fallback = cfg.audit_fallback_skills
        skills = keep(fallback)

    return SkillRouteResult(
        observed=observed,
        matches=tuple(matches),
        skills=tuple(skills[: cfg.max_skills]),
        used_fallback=used_fallback,
    )


@function_tool
async def route_skills(ctx: RunContextWrapper, observed: str) -> str:
    """Deterministically map observed fingerprints to the skills to load.

    Call this BEFORE load_skill whenever you spot a technology, protection layer,
    protocol, client type, or bug class on the target (white-box: a code smell,
    sink, or framework). It returns the exact, curator-defined skill set for that
    fingerprint (no guessing), which you should then load with `load_skill`, or
    hand to `create_agent(skills=[...])` for a child.

    Args:
        observed: free-text description of what you observed, e.g.
            "站点返回 412 且带动态 cookie 与 _ts 脚本" or "对象存储 STS 领签接口"
            (white-box: "白盒 源码审计 semgrep 静态分诊" or "依赖 CVE 供应链").

    Returns:
        JSON with matched routes, the ordered skill list (max 5), and a hint.
    """
    mode = _runtime_mode(ctx)
    result = match_skills(observed, mode=mode)
    payload: dict[str, Any] = {
        "observed": result.observed,
        "matched_routes": [
            {"id": m.route_id, "note": m.note, "signal_hits": list(m.hits), "skills": list(m.skills)}
            for m in result.matches
        ],
        "skills": list(result.skills),
        "used_fallback": result.used_fallback,
    }
    if result.used_fallback:
        payload["hint"] = (
            "无匹配指纹：先 load_skill('custom/source_aware_sast') 按白盒静态分诊流程起手。"
            if mode == RuntimeMode.SOURCE_AUDIT
            else "无指纹命中：先 load_skill('src_hunt/打穿短表') 按索引决定开场几枪。"
        )
    else:
        payload["hint"] = "用 load_skill 读这些技能（最多 5 个），或把它们交给 create_agent(skills=[...])。"
    return json.dumps(payload, ensure_ascii=False)


def _runtime_mode(ctx: RunContextWrapper) -> RuntimeMode:
    """从运行时上下文取本次作战模式；取不到按渗透处理（保持既有行为）。"""
    context = getattr(ctx, "context", None)
    value = context.get("strix_mode") if isinstance(context, dict) else None
    if value == RuntimeMode.SOURCE_AUDIT or value == RuntimeMode.SOURCE_AUDIT.value:
        return RuntimeMode.SOURCE_AUDIT
    return RuntimeMode.PENETRATION


# 挂给 ravenholt root/child 的路由工具（不依赖沙箱 / 项目绑定）。
SKILL_ROUTE_TOOLS: tuple[Any, ...] = (route_skills,)


__all__ = [
    "DEFAULT_ROUTES_FILE",
    "INSTANCE_ROUTES_FILE",
    "SKILL_ROUTE_TOOLS",
    "RouteMatch",
    "SkillRouteResult",
    "SkillRoutesError",
    "get_skill_routes",
    "instance_routes_path",
    "load_skill_routes",
    "match_skills",
    "merge_routes",
    "reload_skill_routes",
    "route_skills",
    "routes_source",
    "unknown_skills",
]
