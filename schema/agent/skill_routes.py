"""确定性技能路由（``skill_routes.yaml``）的 pydantic 模型。

路由表是**数据**而非代码：工厂默认在 ``core/strix_runtime/skill_routes.default.yaml``，
实例可在 ``.ravenholt/skill_routes.yaml`` 覆盖。这里只约束结构，不做语义裁决。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    # 与 config.py / policy.py 同款：多写字段直接报错，避免拼错的配置被静默忽略
    model_config = ConfigDict(extra="forbid")


class SkillRoute(StrictModel):
    """一条路由：命中任一 ``signals`` 即把 ``skills`` 推荐给 agent。"""

    id: str = Field(min_length=1)
    note: str = ""
    # 小写子串匹配；agent 给出的现场观察里含任一即命中
    signals: list[str] = Field(default_factory=list)
    # 限定名 ``src_hunt/<技能>``，避免与内置技能重名歧义
    skills: list[str] = Field(default_factory=list)


class SkillRoutesConfig(StrictModel):
    version: int = Field(default=1, ge=1)
    # 与 strix 加载器一致：单次最多 5 个技能
    max_skills: int = Field(default=5, ge=1)
    # 一条都没命中时兜底的索引技能（照 src-hunt 做法先读短表）
    fallback_skills: list[str] = Field(default_factory=lambda: ["src_hunt/打穿短表"])
    # 白盒（源码审计）会话的兜底技能；为空则沿用 fallback_skills
    audit_fallback_skills: list[str] = Field(default_factory=list)
    # 实例覆盖表可用它屏蔽工厂默认里的若干条（按 id）
    disabled_routes: list[str] = Field(default_factory=list)
    routes: list[SkillRoute] = Field(default_factory=list)


__all__ = ["SkillRoute", "SkillRoutesConfig"]
