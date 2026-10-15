"""把 ravenholt 运行时的状态与流事件投影到 ravenholt 统一事件总线。

两条投影通路：
- **流事件**：复用 ``core.runtime.events.SdkStreamEventNormalizer``，按 agent 独立分段，
  归一为 ToolCall / ToolResult / Text / Thinking / Error 事件，直接落进会话时间线。
- **图状态**：轮询 ``AgentCoordinator`` 快照，在子代理状态变化时发出 ``SubagentTaskEvent``，
  驱动操作台的 agent 图 / 子代理侧栏（root 本身不投影为子代理任务）。

投影只做「读取 + 转发」，不修改 ravenholt 运行时状态。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.runtime.events import SdkStreamEventNormalizer
from schema.agent.events import AgentEventSchema, SubagentTaskEvent
from schema.agent.subordinates import AgentSubordinateStatus


logger = logging.getLogger(__name__)

# 协调器的生命周期状态 → ravenholt 子代理任务状态。
_STATUS_MAP: dict[str, AgentSubordinateStatus] = {
    "running": AgentSubordinateStatus.RUNNING,
    "waiting": AgentSubordinateStatus.RUNNING,
    "budget_paused": AgentSubordinateStatus.RUNNING,
    "completed": AgentSubordinateStatus.COMPLETED,
    "stopped": AgentSubordinateStatus.CANCELED,
    "crashed": AgentSubordinateStatus.FAILED,
    "failed": AgentSubordinateStatus.FAILED,
}

_GRAPH_POLL_INTERVAL_SECONDS = 0.4


class StrixEventProjector:
    """把一个运行时 run 的事件流投影为 ravenholt 事件。

    ``publish`` 接收已归一化的 ``AgentEventSchema``；传入
    ``AgentSession.publish_external`` 即可让事件进入会话总线与持久化时间线。
    """

    def __init__(self, publish: Callable[[AgentEventSchema], Any], *, root_id: str = "root") -> None:
        self._publish = publish
        self._root_id = root_id
        self._normalizers: dict[str, SdkStreamEventNormalizer] = {}
        self._names: dict[str, str] = {}
        self._last_status: dict[str, Any] = {}

    # --- 流事件（event_sink 形态，同步回调） --------------------------------

    def on_stream_event(self, agent_id: str, sdk_event: Any) -> None:
        normalizer = self._normalizers.get(agent_id)
        if normalizer is None:
            normalizer = SdkStreamEventNormalizer(segment_scope=agent_id)
            self._normalizers[agent_id] = normalizer
        event = normalizer.event_from_sdk_stream(sdk_event, self._names.get(agent_id, agent_id))
        if event is not None:
            self._tag_nested(event, agent_id)
            self._emit(event)

    def _tag_nested(self, event: Any, agent_id: str) -> None:
        """把子代理的流事件打上自身 run_id 作 nested_call_id，供前端归集。

        子代理的 agent_id 就是其子代理任务的 run_id，前端据此把思考/正文/工具流挂到
        对应子代理执行块下。root 事件不打标，仍落在主时间线。只改事件字段，不触碰运行时。
        """
        if agent_id == self._root_id or not hasattr(event, "nested_call_id"):
            return
        event.nested_call_id = agent_id

    # --- 图状态（后台轮询任务，直到被取消） --------------------------------

    async def watch_graph(self, coordinator: Any, *, interval: float = _GRAPH_POLL_INTERVAL_SECONDS) -> None:
        """轮询协调器快照并在状态变化时发出子代理任务事件，直到任务被取消。"""
        while True:
            try:
                await self.emit_graph_delta(coordinator)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 投影失败不得影响运行
                logger.exception("strix graph projection failed")
            await asyncio.sleep(interval)

    async def emit_graph_delta(self, coordinator: Any) -> None:
        parent_of, statuses, names, errors = await coordinator.graph_snapshot()
        self._names.update(names)
        for agent_id, status in statuses.items():
            if self._last_status.get(agent_id) == status:
                continue
            self._last_status[agent_id] = status
            parent_id = parent_of.get(agent_id)
            if parent_id is None:
                # root 即会话主代理，不投影为子代理任务。
                continue
            self._emit(
                SubagentTaskEvent(
                    created_at=datetime.now(),
                    agent_name=names.get(agent_id, agent_id),
                    run_id=agent_id,
                    parent_agent_code=names.get(parent_id, "") or parent_id,
                    parent_agent_instance_id=parent_id,
                    agent_code=agent_id,
                    status=_STATUS_MAP.get(status, AgentSubordinateStatus.RUNNING),
                    error_preview=errors.get(agent_id, ""),
                )
            )

    def _emit(self, event: AgentEventSchema) -> None:
        try:
            self._publish(event)
        except Exception:  # noqa: BLE001 - 投影失败不得影响运行
            logger.exception("strix event projection failed")


__all__ = ["StrixEventProjector"]
