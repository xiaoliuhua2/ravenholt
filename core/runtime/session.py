"""Per-conversation Agent runtime: turn execution and pool lifecycle.

执行引擎只有 strix 单轨：回合由 :meth:`AgentSession.start_strix_turn` 直接驱动
（root agent → ``create_agent`` 动态派生 agent 树 → 沙箱 SDK 能力）。原生 registry
轨道的通知邮箱驱动链（``start_turn`` / ``_drive`` / 通知恢复 / 静态子代理图）已整体删除。
"""

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config import get_config
from core.agent.registry import AgentRegistry
from core.delegation.subagents import cancel_sandbox_subagent_runs, cancel_session_subagent_runs
from core.policy.pending_gate import pending_gate
from core.runtime.archive import archive_event
from core.runtime.context import AgentRuntimeContext, main_agent_instance_id
from core.runtime.input_items import display_text_from_content
from core.runtime.live_projection import LiveEventProjection
from core.runtime.timeline import TimelineLogWriter, is_persistable, timeline_item_key
from core.sandbox.command_jobs import cancel_sandbox_async_commands, cancel_session_async_sandbox_commands
from logger import get_logger
from schema.agent.events import (
    AgentEventSchema,
    AgentInputPart,
    DoneEvent,
    ErrorEvent,
    RunStateEvent,
    SandboxEvent,
    SandboxPhaseSchema,
    UserMessageEvent,
)
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)

_SUBSCRIBER_REBASE_THRESHOLD = 512
# Application-defined close code (4000-4999 is the app-specific range). The
# frontend uses it to tell "server restarted the stream after a config update"
# apart from a genuine network drop, so it can reconnect instead of reporting a
# misleading "stream closed before the model produced output" error.
SUBSCRIBER_CLOSED_CODE = 4001


@dataclass(frozen=True)
class SubscriberClosed:
    """Sentinel queued to subscribers when a session tears down its event streams."""

    code: int = SUBSCRIBER_CLOSED_CODE
    reason: str = ""


_SubscriberQueue = asyncio.Queue[AgentEventSchema | SubscriberClosed]


class AgentSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._start_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self._subscribers: set[_SubscriberQueue] = set()
        self._live_projection = LiveEventProjection()
        # per-session timeline log: monotonic seq counter + first-seen key map
        self._seq: int = 0
        self._item_seq: dict[str, int] = {}
        self._timeline_loaded = False
        self._log_writer = TimelineLogWriter(session_id)

    def is_running(self) -> bool:
        task = self._current_task
        return task is not None and not task.done()

    @property
    def timeline_loaded(self) -> bool:
        return self._timeline_loaded

    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    async def subscribe(
        self,
        include: Callable[[AgentEventSchema], bool] | None = None,
    ) -> _SubscriberQueue:
        snapshot = self._live_projection.snapshot(include)
        queue: _SubscriberQueue = asyncio.Queue()
        for event in snapshot:
            queue.put_nowait(event)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: _SubscriberQueue) -> None:
        self._subscribers.discard(queue)

    async def start_strix_turn(
        self,
        task: str,
        context: AgentRuntimeContext,
        *,
        agent_code: str = "",
        display_text: str = "",
        content: list[AgentInputPart] | None = None,
    ) -> list[AgentEventSchema]:
        """启动一次由 ravenholt 运行时驱动的回合（root → create_agent 动态派生 agent 树）。

        复用会话语义：先落 run_state + user_message，再后台跑 ravenholt run loop；运行时的
        子代理图状态与 SDK 流事件经 ``StrixEventProjector`` 投影进统一事件总线，因此
        操作台能看到动态派生的 agent 树与每步工具调用。

        ``content`` 只用于附件：沙箱由运行时按会话自动 provision，图片要在容器就绪后
        才能落盘，因此这里把原始输入交给驱动器而不是提前合成任务文本。
        """
        from schema.agent.events import AgentTextInputPart

        async with self._start_lock:
            if self.is_running():
                raise RuntimeError("session is already running a turn")
            code = agent_code or context.agent_code
            await _mark_session_running(
                self.session_id,
                agent_code=code,
                sandbox_container_id=context.sandbox_container_id,
                sandbox_container_generation=context.sandbox_container_generation,
            )
            await self._ensure_timeline_loaded()
            events: list[AgentEventSchema] = [self._publish_run_state(True)]
            # 气泡只放用户原话：纯图片输入时 task 与 display_text 都可能为空，
            # 而 AgentTextInputPart 要求非空，需要一个占位文案。
            bubble_text = display_text or task or "（图片附件）"
            events.append(await self._publish(UserMessageEvent(
                created_at=datetime.now(),
                content=[AgentTextInputPart(text=bubble_text)],
                display_text=bubble_text,
                target_agent_code=code,
            )))
            self._current_task = asyncio.create_task(
                self._drive_strix(task, context, code, content),
                name=f"strix-turn-{self.session_id}",
            )
            return events

    async def _drive_strix(
        self,
        task: str,
        context: AgentRuntimeContext,
        agent_code: str,
        content: list[AgentInputPart] | None = None,
    ) -> None:
        from config import WORKSPACE, get_config
        from core.strix_runtime import build_configured_model, run_strix_session
        from core.strix_runtime.findings import WorkProjectFindingMirror
        from core.strix_runtime.prompts import (
            RuntimeMode,
            build_child_instructions,
            build_root_instructions,
            mode_for_project_type,
        )
        from core.strix_runtime.projection import StrixEventProjector
        from core.strix_runtime.sandbox_provision import SandboxProvisionError, provision_sandbox
        from strix.report.state import ReportState, set_global_report_state

        root_id = main_agent_instance_id(self.session_id, context.user.id, agent_code)
        # 项目类型决定作战规程：渗透=黑盒 src-hunt（默认），源码审计=白盒 source-aware。
        runtime_mode = mode_for_project_type(context.work_project_type)
        # 源码审计：把项目声明的源码目录挂进沙箱，并把挂载点写进 root 规程。
        local_sources: list[dict[str, Any]] = []
        source_roots: list[str] = []
        skipped_sources: list[str] = []
        if runtime_mode == RuntimeMode.SOURCE_AUDIT and context.work_project_id is not None:
            local_sources, source_roots, skipped_sources = await _collect_source_mounts(
                context.work_project_id
            )
        logger.info(
            "strix turn mode=%s project=%s work_project_type=%s source_roots=%s skipped=%s session=%s",
            runtime_mode.value,
            context.work_project_id,
            context.work_project_type,
            source_roots,
            skipped_sources,
            self.session_id,
        )
        # 项目资产清单 = 本次授权范围。用户原话常常只有「开始测试」，不给这段注入，
        # root 会按规程判定「没有可测目标」转而反问用户。
        scope_targets: list[str] = []
        if context.work_project_id is not None:
            from service.work_project.projects import work_project_scope_targets

            scope_targets = await work_project_scope_targets(context.work_project_id)
        if scope_targets:
            logger.info("strix scope injected project=%s targets=%s", context.work_project_id, scope_targets)
        projector = StrixEventProjector(publish=self.publish_external, root_id=root_id)
        run_dir = WORKSPACE / "strix_runs"
        run_dir.mkdir(parents=True, exist_ok=True)

        agent_cfg = get_config().agents.get(agent_code)
        use_responses = bool(agent_cfg.use_responses) if agent_cfg is not None else False

        # ravenholt 的 finding 汇聚在全局 ReportState；挂上 WorkProject 镜像（草稿态）。
        report_state = ReportState(run_name=self.session_id)
        mirror: WorkProjectFindingMirror | None = None
        if context.work_project_id is not None:
            mirror = WorkProjectFindingMirror(
                project_id=context.work_project_id,
                session_id=self.session_id,
                agent_code=agent_code,
            )
            report_state.vulnerability_found_callback = mirror.on_report
        set_global_report_state(report_state)

        try:
            # 沙箱是硬前提：建容器（含容器内 Caido）→ 过红线闸口 → 会话包闸口 → 回写平台记录。
            # 拿不到沙箱就终止本回合，不降级跑无沙箱的空壳。
            self._publish_sandbox_event(
                SandboxPhaseSchema.PROVISIONING,
                message="正在准备沙箱环境",
            )
            provision = await provision_sandbox(
                session_id=self.session_id,
                owner_id=context.user.id,
                local_sources=local_sources,
            )
            await self._mark_sandbox_ready(provision)
            # 容器就绪后才合成任务文本：图片附件需要落进这个容器（保真通道）。
            runtime_task = await self._build_task_with_attachments(
                task,
                content,
                provision.record_id,
                agent_code,
            )
            if skipped_sources:
                runtime_task = (
                    "范围提示：以下声明的源码路径在服务器上不存在或不可挂载，本次未纳入："
                    + "、".join(skipped_sources)
                    + "\n\n"
                    + runtime_task
                )
            if scope_targets:
                runtime_task = _scope_targets_block(scope_targets) + runtime_task
            await run_strix_session(
                task=runtime_task,
                model=build_configured_model(agent_code, session_id=self.session_id),
                instructions=build_root_instructions(mode=runtime_mode, source_roots=source_roots),
                child_instructions=build_child_instructions(mode=runtime_mode),
                agents_db_path=run_dir / f"{self.session_id}.db",
                sandbox_session=provision.session,
                caido_client=provision.caido_client,
                work_project_id=context.work_project_id,
                session_id=self.session_id,
                root_id=root_id,
                # route_skills 据此选兜底技能（白盒回退 source-aware，而不是渗透短表）。
                extra_context={"strix_mode": runtime_mode.value},
                projector=projector,
                # ravenholt 的模型走 OpenAI 兼容端点：自定义工具包成 function tool、
                # 不启用 strict schema，避免端点拒收导致整轮失败。
                chat_completions_tools=not use_responses,
                strict_tool_schemas=use_responses,
            )
            if mirror is not None:
                await mirror.flush()
        except SandboxProvisionError as exc:
            logger.warning("strix sandbox unavailable session=%s: %s", self.session_id, exc)
            self.publish_external(ErrorEvent(
                created_at=datetime.now(),
                message="沙箱不可用，本次任务未启动。请确认沙箱镜像与容器运行时就绪后重试。",
            ))
        except Exception as exc:
            logger.exception("strix run failed session=%s", self.session_id)
            self.publish_external(ErrorEvent(
                created_at=datetime.now(),
                message=str(exc) or "strix run failed",
            ))
        finally:
            set_global_report_state(None)
            self.publish_external(DoneEvent(created_at=datetime.now()))
            self._publish_run_state(False)
            self._current_task = None
            await _mark_session_stopped(self.session_id)

    def _publish_sandbox_event(
        self,
        phase: SandboxPhaseSchema,
        *,
        container_id: int | None = None,
        container_hash: str = "",
        container_name: str = "",
        image_name: str = "",
        message: str = "",
    ) -> None:
        """把沙箱生命周期事件投进会话事件总线（同时进入时间线，刷新后可回放）。"""
        self.publish_external(SandboxEvent(
            created_at=datetime.now(),
            phase=phase,
            container_id=container_id,
            container_hash=container_hash,
            container_name=container_name,
            image_name=image_name,
            message=message,
        ))

    async def _mark_sandbox_ready(self, provision) -> None:
        """沙箱就绪：回写会话当前沙箱，且只在容器**发生变化**时广播 ready 事件。

        每轮回合都会经过 provision（strix 按会话复用容器），但事件只在首次绑定或换容器
        时发出 —— 否则对话流里每轮都会多出一条重复的"沙箱已就绪"。回写失败只影响前端
        展示（拿不到"当前沙箱"），不阻断本回合执行。
        """
        from service.agent import sessions as agent_sessions

        changed = False
        if provision.record_id is not None:
            try:
                changed = await agent_sessions.update_session_runtime_sandbox(
                    self.session_id,
                    sandbox_container_id=provision.record_id,
                )
            except Exception:
                logger.warning(
                    "sandbox runtime bind write-back failed session=%s",
                    self.session_id,
                    exc_info=True,
                )
        if not changed:
            return
        self._publish_sandbox_event(
            SandboxPhaseSchema.READY,
            container_id=provision.record_id,
            container_hash=provision.container_hash,
            container_name=provision.container_name,
            image_name=provision.image_name,
            message="沙箱已就绪",
        )

    async def _build_task_with_attachments(
        self,
        task: str,
        content: list[AgentInputPart] | None,
        container_id: int | None,
        agent_code: str,
    ) -> str:
        """沙箱就绪后合成任务文本：附件图片落进容器（保真通道）+ 逐字转写（提示通道）。

        任务文本口径：显式 ``task`` 优先，其次取 ``content`` 的文本块（前端富文本统一走
        ``content``，不传 ``task``）。容器记录缺失（回写失败）或写入失败时，明确在任务里
        说明附件未落盘，既不静默丢图，也不让整轮失败。
        """
        from service.agent.attachments import compose_strix_task, image_parts, text_of

        if not image_parts(content):
            # 前端富文本统一走 content：纯文本输入的正文只存在于 content 里，只回 task
            # 会让智能体拿到空任务（表现为「我发了目标，它却说没有目标」）。取文本口径
            # 与下面的图片分支保持一致：显式 task 优先，否则回退 content 的文本块。
            return (task or "").strip() or text_of(content)
        if container_id is None:
            note = "【附件】本次会话的沙箱未能就绪，图片附件没有放进容器，请让用户重新上传。"
            return f"{task}\n\n{note}" if task else note
        try:
            return await compose_strix_task(
                task=task,
                content=content,
                container_id=container_id,
                agent_code=agent_code,
            )
        except Exception:
            logger.warning("attachment persist failed session=%s", self.session_id, exc_info=True)
            note = "【附件】图片附件写入沙箱失败，请让用户重新上传。"
            return f"{task}\n\n{note}" if task else note

    async def interrupt(self) -> list[AgentEventSchema]:
        task = self._current_task
        if task is None or task.done():
            return []
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # 挂起中的审批随之作废：摘掉等待记录，避免留下「永远等不到决策」的悬挂 future。
        pending_gate.discard_session(self.session_id)
        # The cancelled task's teardown already published a terminal ``DoneEvent``
        # so the live projection ends in a finalised state. We only need to (a) drop
        # main-agent notifications the user explicitly abandoned and (b) update
        # session liveness; freshly enqueued USER_MESSAGE notifications are
        # preserved so the next idle cycle still honours them.
        await agent_notifications.cancel_main_agent_interrupted_notifications(
            self.session_id,
            "Discarded by user interrupt.",
        )
        await _mark_session_stopped(self.session_id)
        event = await self._publish_idle_if_inactive()
        return [event] if event is not None else []

    async def cancel_all(self) -> list[AgentEventSchema]:
        events: list[AgentEventSchema] = []
        task = self._current_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await _mark_session_stopped(self.session_id)
            events.append(await self._publish(DoneEvent(created_at=datetime.now())))
        pending_gate.discard_session(self.session_id)
        await cancel_session_subagent_runs(self.session_id)
        await cancel_session_async_sandbox_commands(self.session_id)
        await agent_notifications.cancel_session_notifications(
            self.session_id,
            "Agent session tasks canceled by user.",
        )
        await _force_mark_session_stopped(self.session_id)
        events.append(self._publish_run_state(False))
        return events

    async def shutdown(self, *, code: int = SUBSCRIBER_CLOSED_CODE, reason: str = "") -> None:
        await self.cancel_all()
        await self.close(code=code, reason=reason)

    async def close(self, *, code: int = SUBSCRIBER_CLOSED_CODE, reason: str = "") -> None:
        self._close_subscribers(code=code, reason=reason)
        await self._log_writer.stop()
        self._timeline_loaded = False

    def _close_subscribers(self, *, code: int = SUBSCRIBER_CLOSED_CODE, reason: str = "") -> None:
        for queue in tuple(self._subscribers):
            queue.put_nowait(SubscriberClosed(code=code, reason=reason))
        self._subscribers.clear()

    async def flush_timeline(self) -> None:
        if self._timeline_loaded:
            await self._log_writer.flush()

    def uses_sandbox_container(self, container_id: int) -> bool:
        # strix 单轨：沙箱按回合 provision，会话不长期绑定任何容器。
        return False

    async def invalidate_tool_binding(self) -> None:
        await self.cancel_all()

    def _publish_run_state(self, running: bool) -> RunStateEvent:
        event = RunStateEvent(created_at=datetime.now(), running=running)
        # 运行状态帧不经 publish_external（直接投递订阅者），旁路归档需单独挂一次，
        # 否则监控器会缺失「回合开始 / 结束」这两个边界。
        archive_event(self.session_id, event)
        if running:
            self._live_projection.reset(event)
        else:
            self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            self._enqueue_or_rebase(queue, event)
        if not running:
            self._live_projection.reset(event)
        return event

    async def _publish_idle_if_inactive(self) -> RunStateEvent | None:
        # Live run-state tracks the main agent only (idle-live UX): once it ends
        # with no claimable PENDING turn, go idle even while sub-agents stream.
        if self.is_running():
            return None
        if await agent_notifications.has_pending_main_agent_notification(session_id=self.session_id):
            return None
        return self._publish_run_state(False)

    async def _publish(self, event: AgentEventSchema) -> AgentEventSchema:
        self.publish_external(event)
        return event

    async def _ensure_timeline_loaded(self) -> None:
        """Resume the seq counter + key map from the durable log, then start the writer.

        Loading the existing key→seq map lets a re-pooled or recovered session
        re-emit an already-persisted item (e.g. a running subagent_task) under
        its original seq so live and stored frames keep one identity space.
        """
        if self._timeline_loaded:
            return
        from service.agent.event_log import load_timeline_head

        max_seq, item_seq = await load_timeline_head(self.session_id)
        if self._timeline_loaded:
            return
        self._seq = max(self._seq, max_seq)
        for key, seq in item_seq.items():
            self._item_seq.setdefault(key, seq)
        self._timeline_loaded = True
        self._log_writer.start()

    def _stamp_event(self, event: AgentEventSchema) -> str | None:
        """Stamp ``event.seq`` in place; return its durable item_key or None.

        Keyless events (user_message/turn_boundary/error) consume a fresh seq
        per emission; keyed events reuse the first-seen seq for their item_key.
        Deltas and control frames receive a seq for ordering but are not stored.
        """
        if isinstance(event, (RunStateEvent, DoneEvent)):
            return None
        key = timeline_item_key(event)
        if key is None:
            self._seq += 1
            event.seq = self._seq
            persist_key = f"{event.type}:{self._seq}"
        else:
            seq = self._item_seq.get(key)
            if seq is None:
                self._seq += 1
                seq = self._seq
                self._item_seq[key] = seq
            event.seq = seq
            persist_key = key
        if not is_persistable(event):
            return None
        return persist_key

    def publish_external(self, event: AgentEventSchema) -> bool:
        """Inject an event into the session's unified event bus.

        Used internally by ``_publish`` and externally via ``AgentSessionPool.publish``.
        Returns whether a persistable event was accepted by the durable writer;
        non-persistable control/delta frames return ``True`` once delivered to
        subscribers/projection.
        """
        persist_key = self._stamp_event(event)
        # 旁路归档在「持久化过滤」之前：delta / 控制帧不进时间线，但必须进归档，
        # 因此这里无条件写一条原始帧（含 seq 已就地写入 event.seq）。
        archive_event(self.session_id, event)
        self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            self._enqueue_or_rebase(queue, event)
        if persist_key is not None and self._timeline_loaded:
            return self._log_writer.enqueue(persist_key, event.seq, event.model_dump_json(), event.created_at)
        return persist_key is None

    def _enqueue_or_rebase(self, queue: _SubscriberQueue, event: AgentEventSchema) -> None:
        if queue.qsize() < _SUBSCRIBER_REBASE_THRESHOLD:
            queue.put_nowait(event)
            return

        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        snapshot = self._live_projection.snapshot()
        if isinstance(event, RunStateEvent) and not event.running:
            snapshot = [item for item in snapshot if not isinstance(item, RunStateEvent)]
            snapshot.append(event)
        for item in snapshot:
            queue.put_nowait(item)


@dataclass
class _PooledSession:
    session: AgentSession
    last_used_at: float = field(default_factory=time.monotonic)


@dataclass(frozen=True)
class _EvictionCandidate:
    session_id: str
    entry: _PooledSession
    last_used_at: float


class AgentSessionPool:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        cfg = get_config().agent_pool
        self._registry = registry or AgentRegistry()
        self._max_size = cfg.max_size
        self._ttl = cfg.ttl_seconds
        self._sweep_interval = cfg.sweep_interval_seconds
        self._pool: dict[str, _PooledSession] = {}
        self._sweeper_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    async def start(self) -> None:
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweep_loop(), name="agent-pool-sweeper")
        logger.debug(
            "agent pool started (ttl=%ds, interval=%ds, max_size=%d)",
            self._ttl, self._sweep_interval, self._max_size,
        )

    async def stop(self, *, reason: str = "") -> None:
        task, self._sweeper_task = self._sweeper_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            entries = list(self._pool.values())
            session_ids = list(self._pool.keys())
            self._pool.clear()
        await asyncio.gather(
            *(entry.session.shutdown(reason=reason) for entry in entries),
            return_exceptions=True,
        )
        await _mark_sessions_stopped(session_ids)
        logger.debug("agent pool stopped")

    def has_running_sessions(self) -> bool:
        return any(entry.session.is_running() for entry in self._pool.values())

    async def get_or_create(self, session_id: str) -> AgentSession:
        async with self._lock:
            session = self._get_or_create_locked(session_id)
        await self._enforce_capacity(protected_session_id=session_id)
        return session

    async def _enforce_capacity(self, *, protected_session_id: str = "") -> None:
        async with self._lock:
            candidates = self._capacity_candidates_locked(protected_session_id=protected_session_id)
            overflow = max(0, len(self._pool) - self._max_size)
        evicted = await self._claim_inactive_evictions(candidates, limit=overflow)
        await self._close_evicted(evicted, reason="LRU")

    def _get_or_create_locked(self, session_id: str) -> AgentSession:
        entry = self._pool.get(session_id)
        if entry is None:
            entry = _PooledSession(session=AgentSession(session_id))
            self._pool[session_id] = entry
            logger.debug("agent pool created session=%s", session_id)
        else:
            entry.last_used_at = time.monotonic()
        return entry.session

    async def discard(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.pop(session_id, None)
        if entry is None:
            await _force_mark_session_stopped(session_id)
            return
        await entry.session.shutdown()
        logger.debug("agent pool discarded session=%s", session_id)

    async def invalidate_session_tool_binding(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            return
        await entry.session.invalidate_tool_binding()

    async def flush_timeline(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is not None:
            await entry.session.flush_timeline()

    async def try_interrupt(self, session_id: str) -> list[AgentEventSchema]:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            return []
        return await entry.session.interrupt()

    async def subscribe(
        self,
        session_id: str,
        include: Callable[[AgentEventSchema], bool] | None = None,
    ) -> tuple[AgentSession, _SubscriberQueue]:
        session = await self.get_or_create(session_id)
        return session, await session.subscribe(include)

    def publish(self, session_id: str, event: AgentEventSchema) -> bool:
        """Route an external event to the session's unified event bus.

        Lock-free: dict.get and attribute assignment are atomic in asyncio's
        single-threaded model. Returns ``True`` when a pooled session with a
        loaded timeline received and durably stored the event; ``False`` lets
        the caller fall back to a direct persist (e.g. boot-time subagent
        status changes for sessions that are not pooled yet).
        """
        entry = self._pool.get(session_id)
        if entry is None:
            return False
        entry.last_used_at = time.monotonic()
        return entry.session.publish_external(event)

    async def resume_session(self, session_id: str) -> None:
        # strix 单轨：回合由进程内的 strix run loop 承载，没有通知邮箱驱动的待办回合，
        # 因此恢复语义退化为把会话收敛为空闲（标记 DB 停止 + 广播 run_state=false）。
        await self._settle_session_idle(session_id)

    async def _settle_session_idle(self, session_id: str) -> None:
        # Wind down a session with no pending main turn (e.g. a canceled task):
        # mark the DB run stopped (no-op while other work is active) and publish
        # run_state=false for a pooled, non-running session.
        entry = self._pool.get(session_id)
        if entry is not None and entry.session.is_running():
            return
        await _mark_session_stopped(session_id)
        if entry is not None:
            await entry.session._publish_idle_if_inactive()

    async def cancel_all(self, session_id: str) -> list[AgentEventSchema]:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            await cancel_session_subagent_runs(session_id)
            await cancel_session_async_sandbox_commands(session_id)
            await agent_notifications.cancel_session_notifications(
                session_id,
                "Agent session tasks canceled by user.",
            )
            await _force_mark_session_stopped(session_id)
            return []
        return await entry.session.cancel_all()

    async def invalidate_tool_bindings(self, container_id: int | None = None) -> None:
        async with self._lock:
            entries = [
                entry for entry in self._pool.values()
                if container_id is None or entry.session.uses_sandbox_container(container_id)
            ]
        tasks = [entry.session.invalidate_tool_binding() for entry in entries]
        if container_id is not None:
            tasks.extend([
                cancel_sandbox_subagent_runs(container_id),
                cancel_sandbox_async_commands(container_id),
            ])
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug("agent pool invalidated tool bindings container=%s count=%d", container_id, len(entries))

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                async with self._lock:
                    expired = self._sweep_expired_candidates_locked(time.monotonic())
                expired = await self._claim_inactive_evictions(expired)
                await self._close_evicted(expired, reason="idle")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent pool sweep iteration failed")

    def _sweep_expired_candidates_locked(self, now: float) -> list[_EvictionCandidate]:
        if self._ttl <= 0:
            return []
        return [
            _EvictionCandidate(sid, entry, entry.last_used_at) for sid, entry in self._pool.items()
            if (
                not entry.session.is_running()
                and not entry.session.has_subscribers()
                and now - entry.last_used_at > self._ttl
            )
        ]

    def _capacity_candidates_locked(self, *, protected_session_id: str = "") -> list[_EvictionCandidate]:
        # only idle entries are evicted; running sessions may briefly exceed the cap
        overflow = len(self._pool) - self._max_size
        if overflow <= 0:
            return []
        return sorted(
            (
                _EvictionCandidate(sid, entry, entry.last_used_at)
                for sid, entry in self._pool.items()
                if (
                    sid != protected_session_id
                    and not entry.session.is_running()
                    and not entry.session.has_subscribers()
                )
            ),
            key=lambda item: item.last_used_at,
        )

    async def _claim_inactive_evictions(
        self,
        candidates: list[_EvictionCandidate],
        limit: int | None = None,
    ) -> list[tuple[str, _PooledSession]]:
        if not candidates or limit == 0:
            return []
        eviction_ids: list[str] = []
        for candidate in candidates:
            if limit is not None and len(eviction_ids) >= limit:
                break
            sid = candidate.session_id
            entry = candidate.entry
            if entry.session.is_running() or entry.session.has_subscribers():
                continue
            if entry.last_used_at != candidate.last_used_at:
                continue
            if await agent_notifications.has_active_session_notifications(session_id=sid):
                continue
            eviction_ids.append(sid)
        if not eviction_ids:
            return []

        observed_last_used = {candidate.session_id: candidate.last_used_at for candidate in candidates}
        evicted: list[tuple[str, _PooledSession]] = []
        async with self._lock:
            for sid in eviction_ids:
                entry = self._pool.get(sid)
                if entry is None:
                    continue
                if entry.session.is_running() or entry.session.has_subscribers():
                    continue
                observed = observed_last_used.get(sid)
                if observed is None or entry.last_used_at != observed:
                    continue
                evicted.append((sid, self._pool.pop(sid)))
        return evicted

    async def _close_evicted(self, evicted: list[tuple[str, _PooledSession]], *, reason: str) -> None:
        if not evicted:
            return
        await asyncio.gather(*(entry.session.close() for _, entry in evicted), return_exceptions=True)
        for sid, _ in evicted:
            logger.debug("agent pool evicted %s session=%s", reason, sid)


_pool: AgentSessionPool | None = None


def get_agent_pool() -> AgentSessionPool:
    global _pool
    if _pool is None:
        _pool = AgentSessionPool()
    return _pool


def replace_agent_pool(pool: AgentSessionPool | None = None) -> AgentSessionPool:
    global _pool
    _pool = pool or AgentSessionPool()
    return _pool


def get_agent_registry() -> AgentRegistry:
    return get_agent_pool().registry


async def _mark_session_running(
    session_id: str,
    *,
    agent_code: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
) -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_running(
        session_id,
        agent_code=agent_code,
        sandbox_container_id=sandbox_container_id,
        sandbox_container_generation=sandbox_container_generation,
    )


async def _mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_stopped(session_id, error=error)


async def _force_mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.force_mark_session_stopped(session_id, error=error)


async def _mark_sessions_stopped(session_ids: list[str], *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_sessions_stopped(session_ids, error=error)


async def _collect_source_mounts(
    project_id: int,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """项目的 binary 资产 → 沙箱挂载条目。

    返回 ``(local_sources, workspace_subdirs, skipped_paths)``：只有**服务器上真实存在、
    且不是系统/家目录/凭证目录**的路径才会挂载（校验复用 strix 的 ``check_mountable_dir``）；
    其余收集进 ``skipped_paths`` 交给调用方提示，不阻断整轮。
    """
    from service.work_project.projects import work_project_source_paths
    from strix.interface.utils import check_mountable_dir

    local_sources: list[dict[str, Any]] = []
    roots: list[str] = []
    skipped: list[str] = []
    used: set[str] = set()
    for path in await work_project_source_paths(project_id):
        try:
            check_mountable_dir(Path(path))
        except ValueError as exc:
            logger.warning("source path is not mountable project=%s path=%s: %s", project_id, path, exc)
            skipped.append(path)
            continue
        subdir = _unique_subdir(_mount_subdir(Path(path).name), used)
        local_sources.append({
            "source_path": path,
            "workspace_subdir": subdir,
            "protect_metadata": True,
            "read_only": False,
        })
        roots.append(subdir)
    if local_sources:
        logger.info("source mounts ready project=%s roots=%s", project_id, roots)
    return local_sources, roots, skipped


def _scope_targets_block(targets: list[str]) -> str:
    """把项目资产清单写成任务前置段。

    清单是「基线范围」而不是穷尽范围：用户在同一条消息里另外点名的目标同样有效，
    否则 root 会把用户追加的目标判成越界。每回合都按当前项目数据重新注入，因此
    历史里可能有多份同类清单，这里声明以本条（最新）为准，避免资产删改后仍按旧清单走。
    """
    listing = "\n".join(f"- {target}" for target in targets)
    return (
        "【授权测试范围（来自工作项目资产清单，由平台按当前项目数据注入，以本条为最新）】\n"
        f"{listing}\n"
        "以上是项目登记的基线范围；若本条用户消息另外点名了目标（域名 / URL / IP / 网段），"
        "一并纳入本次授权范围。两者都在范围内，不要反问用户目标或范围。\n\n"
    )


def _mount_subdir(name: str) -> str:
    """目录名 → 安全的沙箱挂载名（``/workspace/<subdir>``）。"""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip(".-")
    return cleaned[:64] or "source"


def _unique_subdir(name: str, used: set[str]) -> str:
    candidate = name
    index = 2
    while candidate in used:
        candidate = f"{name}-{index}"
        index += 1
    used.add(candidate)
    return candidate
