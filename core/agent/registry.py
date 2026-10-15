"""Agent code registry (single-track: strix runtime).

原生 registry 轨道（``specs`` / ``instructions`` / 六个静态专家 agent 与
``SessionAgentGraph``）已随 strix 单轨化整体退役。本模块只保留平台仍需要的
**只读 code 视图**：agent 列表接口与会话 meta 校验都靠它判断"某个 agent code
是否已配置"。
"""

from __future__ import annotations

from config import get_config


class AgentRegistry:
    """已配置 agent code 的只读视图。"""

    def __init__(self) -> None:
        self._codes_cache: tuple[str, ...] | None = None
        self._code_to_name_cache: dict[str, str] | None = None

    def codes(self) -> list[str]:
        if self._codes_cache is None:
            self._codes_cache = tuple(get_config().agents.keys())
        return list(self._codes_cache)

    def code_to_name(self) -> dict[str, str]:
        if self._code_to_name_cache is None:
            cfg = get_config()
            self._code_to_name_cache = {code: cfg.agents[code].name for code in self.codes()}
        return self._code_to_name_cache

    def has(self, agent_code: str) -> bool:
        return agent_code in self.codes()
