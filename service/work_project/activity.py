"""按真实事件日志重建工作项目的任务、Agent 摘要与进度。

单轨化后 ``work_projects.tasks`` / ``agent_summaries`` / ``progress`` 三列没有任何写入方，
但项目里真实发生过的任务与 agent 活动都落在 ``agent_event_log``：

* ``create_todo`` / ``update_todo`` / ``mark_todo_done`` 的 tool_call 及其 tool_result
  —— 结果里是权威快照，含 ``todo_id`` / ``title`` / ``description`` / ``priority`` /
  ``status`` 的完整列表；
* ``sa``（``subagent_task``）事件 —— 主控派发的子代理任务、终态与派发时的真实任务描述
  （来自配对的 ``create_agent`` 调用参数）；
* 每条事件上的 ``agent_name`` —— 真实干活的 agent 身份，以及它的工具调用次数与最后活动时间。

本模块在读取时用这些记录重建列表，全程只读、不写库。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import and_, cast, func, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import select

from model.agent.event_log import AgentEventLog
from model.agent.sessions import AgentSessionMeta
from model.work_project.findings import WorkProjectFinding
from schema.work_project.projects import (
    WorkProjectAgentSummaryContentSchema,
    WorkProjectAgentSummarySchema,
    WorkProjectTaskSchema,
    WorkProjectTaskStatus,
)


ROOT_AGENT_NAME = "Root Agent"

_TODO_TOOLS = ("create_todo", "update_todo", "mark_todo_done")
_CREATE_AGENT_TOOL = "create_agent"

# todo 工具返回的状态取值（strix 侧为 pending/in_progress/done）
_TODO_STATUS = {
    "pending": WorkProjectTaskStatus.TODO,
    "todo": WorkProjectTaskStatus.TODO,
    "in_progress": WorkProjectTaskStatus.IN_PROGRESS,
    "blocked": WorkProjectTaskStatus.BLOCKED,
    "done": WorkProjectTaskStatus.DONE,
    "completed": WorkProjectTaskStatus.DONE,
    "canceled": WorkProjectTaskStatus.CANCELED,
    "cancelled": WorkProjectTaskStatus.CANCELED,
}
# 子代理任务终态（schema.agent.subordinates.AgentSubordinateStatus）
_SUBAGENT_STATUS = {
    "running": WorkProjectTaskStatus.IN_PROGRESS,
    "completed": WorkProjectTaskStatus.DONE,
    "failed": WorkProjectTaskStatus.BLOCKED,
    "canceled": WorkProjectTaskStatus.CANCELED,
}
_SUBAGENT_TASK_STATUS_TEXT = {
    WorkProjectTaskStatus.TODO: "子代理任务待执行",
    WorkProjectTaskStatus.IN_PROGRESS: "子代理运行中",
    WorkProjectTaskStatus.DONE: "子代理已完成",
    WorkProjectTaskStatus.BLOCKED: "子代理失败",
    WorkProjectTaskStatus.CANCELED: "子代理已取消",
}

_TITLE_LIMIT = 255
_SUMMARY_LIMIT = 4000
_TEXT_LIMIT = 2000
_NOTES_LIMIT = 4000
_AGENT_CODE_LIMIT = 32
_ITEMS_LIMIT = 64


@dataclass
class ProjectActivity:
    """一个项目按真实事件日志重建出的任务与 agent 摘要，以及会话运行终态。"""

    tasks: list[WorkProjectTaskSchema] = field(default_factory=list)
    agent_summaries: list[WorkProjectAgentSummarySchema] = field(default_factory=list)
    # 会话生命周期：项目"跑没跑完"的真实判据（比任务勾选比例可靠）
    has_sessions: bool = False
    any_session_running: bool = False
    all_sessions_finished_cleanly: bool = False


@dataclass
class _AgentActivity:
    tool_calls: int = 0
    events: int = 0
    last_at: datetime | None = None


async def derive_project_activity_in_tx(
    session,
    project_ids: list[int],
) -> dict[int, ProjectActivity]:
    """按项目批量重建任务与 agent 摘要；无会话的项目返回空活动。"""
    ids = [project_id for project_id in project_ids if project_id > 0]
    if not ids:
        return {}

    sessions = (await session.exec(
        select(AgentSessionMeta).where(AgentSessionMeta.project_id.in_(ids))
    )).all()
    empty = {project_id: ProjectActivity() for project_id in ids}
    if not sessions:
        return empty

    session_ids = [meta.session_id for meta in sessions]
    todo_tasks = await _todo_tasks_in_tx(session, session_ids)
    subagent_briefs = await _subagent_briefs_in_tx(session, session_ids)
    subagent_tasks = await _subagent_tasks_in_tx(session, session_ids, subagent_briefs)
    agent_activity = await _agent_activity_in_tx(session, session_ids)
    findings = await _findings_in_tx(session, ids)

    result = {project_id: ProjectActivity() for project_id in ids}
    session_by_id = {meta.session_id: meta for meta in sessions}
    clean_finish: dict[int, list[bool]] = {}
    for meta in sessions:
        activity = result.get(meta.project_id or 0)
        if activity is None:
            continue
        activity.has_sessions = True
        activity.any_session_running = activity.any_session_running or meta.is_running
        clean_finish.setdefault(meta.project_id or 0, []).append(_session_finished_cleanly(meta))

    for session_id, meta in session_by_id.items():
        project_id = meta.project_id or 0
        if project_id not in result:
            continue
        activity = result[project_id]
        session_tasks = todo_tasks.get(session_id, []) + subagent_tasks.get(session_id, [])
        activity.tasks.extend(session_tasks)

        activity.agent_summaries.extend(_summaries_for_session(
            meta=meta,
            tasks=session_tasks,
            subagent_tasks=subagent_tasks.get(session_id, []),
            activity_by_agent=agent_activity.get(session_id, {}),
            findings=findings.get(project_id, []),
        ))

    for project_id, flags in clean_finish.items():
        result[project_id].all_sessions_finished_cleanly = all(flags)

    for activity in result.values():
        activity.agent_summaries.sort(
            key=lambda item: (item.agent_code != ROOT_AGENT_NAME, _descending(item.updated_at)),
        )
    return result


def _session_finished_cleanly(meta: AgentSessionMeta) -> bool:
    """会话已跑完且无运行错误：非运行中、run_finished_at 已落值、run_error 为空。"""
    return not meta.is_running and meta.run_finished_at is not None and not meta.run_error.strip()


def _descending(value: datetime | None) -> float:
    return -(value.timestamp()) if value is not None else float("inf")


# ── 真实 TODO 任务（create_todo / update_todo / mark_todo_done 的权威结果快照） ──


async def _todo_tasks_in_tx(session, session_ids: list[str]) -> dict[str, list[WorkProjectTaskSchema]]:
    call_ids = await _todo_call_ids_in_tx(session, session_ids)
    if not call_ids:
        return {}

    rows = (await session.exec(
        select(AgentEventLog)
        .where(AgentEventLog.session_id.in_(session_ids))
        .where(AgentEventLog.item_key.like("tr:%"))
        .where(or_(*[AgentEventLog.item_key.like(f"%{call_id}") for call_id in sorted(call_ids)]))
        .order_by(AgentEventLog.seq)
    )).all()

    # 同一 todo_id 在后续快照里覆盖前值：最后出现的那次即最终状态。
    tasks: dict[str, dict[str, WorkProjectTaskSchema]] = {}
    for row in rows:
        payload = _payload(row.payload)
        call_id = str(payload.get("call_id") or "")
        owner = call_ids.get(call_id)
        if owner is None:
            continue
        session_id, agent_name = owner
        for item in _todo_items(payload):
            todo_id = str(item.get("todo_id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not todo_id and not title:
                continue
            key = todo_id or title
            tasks.setdefault(session_id, {})[f"{agent_name}:{key}"] = WorkProjectTaskSchema(
                id=_clip(key, 64) or title[:64],
                title=_clip(title or key, _TITLE_LIMIT),
                status=_todo_status(item.get("status")),
                assignee=_clip(agent_name, 128),
                progress=100 if _todo_status(item.get("status")) == WorkProjectTaskStatus.DONE else 0,
                summary=_clip(str(item.get("description") or ""), _SUMMARY_LIMIT),
            )
    return {session_id: list(items.values()) for session_id, items in tasks.items()}


async def _todo_call_ids_in_tx(session, session_ids: list[str]) -> dict[str, tuple[str, str]]:
    """映射 todo 工具的 call_id → (session_id, agent_name)。"""
    rows = (await session.exec(
        select(AgentEventLog)
        .where(AgentEventLog.session_id.in_(session_ids))
        .where(_tool_call_condition(_TODO_TOOLS))
        .order_by(AgentEventLog.seq)
    )).all()
    call_ids: dict[str, tuple[str, str]] = {}
    for row in rows:
        payload = _payload(row.payload)
        call_id = str(payload.get("call_id") or "").strip()
        if not call_id:
            continue
        call_ids[call_id] = (row.session_id, str(payload.get("agent_name") or "").strip())
    return call_ids


def _todo_items(payload: dict) -> list[dict]:
    output = payload.get("output")
    if isinstance(output, str) and output.strip():
        try:
            decoded = json.loads(output)
        except ValueError:
            return []
    elif isinstance(output, dict):
        decoded = output
    else:
        return []
    if not isinstance(decoded, dict):
        return []
    items = decoded.get("todos")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _todo_status(value: object) -> WorkProjectTaskStatus:
    return _TODO_STATUS.get(str(value or "").strip().lower(), WorkProjectTaskStatus.TODO)


# ── 真实子代理任务（sa 事件 + create_agent 的任务描述） ──


async def _subagent_briefs_in_tx(session, session_ids: list[str]) -> dict[tuple[str, str], list[str]]:
    """create_agent 的真实任务描述，按 (session, 子代理名) 依派发顺序排队。"""
    rows = (await session.exec(
        select(AgentEventLog)
        .where(AgentEventLog.session_id.in_(session_ids))
        .where(_tool_call_condition((_CREATE_AGENT_TOOL,)))
        .order_by(AgentEventLog.seq)
    )).all()
    briefs: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        payload = _payload(row.payload)
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            continue
        name = str(arguments.get("name") or "").strip()
        if not name:
            continue
        briefs.setdefault((row.session_id, name), []).append(str(arguments.get("task") or ""))
    return briefs


async def _subagent_tasks_in_tx(
    session,
    session_ids: list[str],
    briefs: dict[tuple[str, str], list[str]],
) -> dict[str, list[WorkProjectTaskSchema]]:
    rows = (await session.exec(
        select(AgentEventLog)
        .where(AgentEventLog.session_id.in_(session_ids))
        .where(AgentEventLog.item_key.like("sa:%"))
        .order_by(AgentEventLog.seq)
    )).all()

    used: dict[tuple[str, str], int] = {}
    tasks: dict[str, list[WorkProjectTaskSchema]] = {}
    for row in rows:
        payload = _payload(row.payload)
        run_id = str(payload.get("run_id") or "").strip()
        agent_name = str(payload.get("agent_name") or "").strip() or run_id
        status_text = str(payload.get("status") or "").strip().lower()
        status = _SUBAGENT_STATUS.get(status_text, WorkProjectTaskStatus.IN_PROGRESS)

        briefs_key = (row.session_id, agent_name)
        index = used.get(briefs_key, 0)
        used[briefs_key] = index + 1
        candidates = briefs.get(briefs_key, [])
        brief = candidates[index] if index < len(candidates) else ""

        parent = str(payload.get("parent_agent_code") or "").strip()
        if brief.strip():
            title = _clip(_first_line(brief), _TITLE_LIMIT)
            summary = _clip(brief, _SUMMARY_LIMIT)
        else:
            title = _clip(f"{agent_name}（子代理任务）", _TITLE_LIMIT)
            summary = _clip(f"派发者：{parent}" if parent else "", _SUMMARY_LIMIT)

        tasks.setdefault(row.session_id, []).append(WorkProjectTaskSchema(
            id=_clip(run_id or agent_name, 64),
            title=title,
            status=status,
            assignee=_clip(agent_name, 128),
            progress=100 if status == WorkProjectTaskStatus.DONE else 0,
            summary=summary,
        ))
    return tasks


# ── 每个 agent 的真实活动量（事件条数 / 工具调用次数 / 最后活动时间） ──


async def _agent_activity_in_tx(session, session_ids: list[str]) -> dict[str, dict[str, _AgentActivity]]:
    agent_name = cast(AgentEventLog.payload, JSONB).op("->>")("agent_name")
    rows = (await session.exec(
        select(
            AgentEventLog.session_id,
            agent_name.label("agent_name"),
            func.count().label("events"),
            func.count().filter(AgentEventLog.item_key.like("tc:%")).label("tool_calls"),
            func.max(AgentEventLog.created_at).label("last_at"),
        )
        .where(AgentEventLog.session_id.in_(session_ids))
        .group_by(AgentEventLog.session_id, agent_name)
    )).all()

    activity: dict[str, dict[str, _AgentActivity]] = {}
    for session_id, name, events, tool_calls, last_at in rows:
        agent = str(name or "").strip()
        if not agent:
            continue
        activity.setdefault(session_id, {})[agent] = _AgentActivity(
            tool_calls=int(tool_calls or 0),
            events=int(events or 0),
            last_at=last_at,
        )
    return activity


async def _findings_in_tx(session, project_ids: list[int]) -> dict[int, list[WorkProjectFinding]]:
    rows = (await session.exec(
        select(WorkProjectFinding)
        .where(WorkProjectFinding.project_id.in_(project_ids))
        .order_by(WorkProjectFinding.id)
    )).all()
    findings: dict[int, list[WorkProjectFinding]] = {}
    for finding in rows:
        findings.setdefault(finding.project_id, []).append(finding)
    return findings


# ── Agent 摘要组装 ──


def _summaries_for_session(
    *,
    meta: AgentSessionMeta,
    tasks: list[WorkProjectTaskSchema],
    subagent_tasks: list[WorkProjectTaskSchema],
    activity_by_agent: dict[str, _AgentActivity],
    findings: list[WorkProjectFinding],
) -> list[WorkProjectAgentSummarySchema]:
    root_code = (meta.runtime_agent_code or meta.agent_code or "").strip()
    # 子代理的真实身份码是它在事件日志里的 run_id（findings.created_by_agent_code 同源）；
    # 同名子代理跑过多轮时保留全部 run_id 用于匹配发现，展示取最近一轮。
    subagent_codes: dict[str, list[str]] = {}
    subagent_status: dict[str, WorkProjectTaskStatus] = {}
    for task in subagent_tasks:
        if not task.assignee:
            continue
        codes = subagent_codes.setdefault(task.assignee, [])
        if task.id not in codes:
            codes.append(task.id)
        subagent_status[task.assignee] = task.status

    agents = set(activity_by_agent) | {task.assignee for task in tasks if task.assignee}
    summaries: list[WorkProjectAgentSummarySchema] = []
    for agent in sorted(agents):
        if not agent:
            continue
        own_codes = subagent_codes.get(agent, [])
        code = root_code if agent == ROOT_AGENT_NAME else (own_codes[-1] if own_codes else "")
        match_codes = {root_code, "", *own_codes} if agent == ROOT_AGENT_NAME else set(own_codes)
        is_root = agent == ROOT_AGENT_NAME
        if is_root:
            status_text = "会话运行中" if meta.is_running else "会话已结束"
        else:
            status_text = _SUBAGENT_TASK_STATUS_TEXT.get(
                subagent_status.get(agent, WorkProjectTaskStatus.IN_PROGRESS),
                "子代理任务进行中",
            )
        if meta.run_error and is_root:
            status_text = f"{status_text}（{_clip(meta.run_error, 200)}）"

        own_tasks = [task for task in tasks if task.assignee == agent]
        done = [task for task in own_tasks if task.status == WorkProjectTaskStatus.DONE]
        pending = [task for task in own_tasks if task.status in (
            WorkProjectTaskStatus.TODO,
            WorkProjectTaskStatus.IN_PROGRESS,
        )]
        stuck = [task for task in own_tasks if task.status in (
            WorkProjectTaskStatus.BLOCKED,
            WorkProjectTaskStatus.CANCELED,
        )]
        current = pending[0] if pending else (own_tasks[-1] if own_tasks else None)

        activity = activity_by_agent.get(agent, _AgentActivity())
        summaries.append(WorkProjectAgentSummarySchema(
            agent_code=_clip(agent, _AGENT_CODE_LIMIT),
            updated_at=activity.last_at,
            summary=WorkProjectAgentSummaryContentSchema(
                task_id=_clip(current.id, 64) if current is not None else "",
                task_title=_clip(current.title, _TITLE_LIMIT) if current is not None else "",
                progress=round(len(done) / len(own_tasks) * 100, 2) if own_tasks else 0,
                status=_clip(status_text, _TEXT_LIMIT),
                findings=[_clip(finding.title, _TITLE_LIMIT) for finding in findings
                          if finding.created_by_agent_code in match_codes][:_ITEMS_LIMIT],
                decisions=[],
                blockers=[_clip(task.title, _TITLE_LIMIT) for task in stuck][:_ITEMS_LIMIT],
                next_steps=[_clip(task.title, _TITLE_LIMIT) for task in pending][:_ITEMS_LIMIT],
                notes=_agent_notes(code=code, activity=activity),
            ),
        ))
    return summaries


def _agent_notes(*, code: str, activity: _AgentActivity) -> str:
    parts = []
    if code:
        parts.append(f"身份 {code}")
    parts.append(f"工具调用 {activity.tool_calls} 次")
    parts.append(f"事件 {activity.events} 条")
    return _clip("；".join(parts), _NOTES_LIMIT)


# ── 通用工具 ──


def _tool_call_condition(names: tuple[str, ...]):
    """tool_call 事件且 name 命中给定工具名（json 分隔符有两种写法）。"""
    conditions = []
    for name in names:
        conditions.append(AgentEventLog.payload.like(f'%"name":"{name}"%'))
        conditions.append(AgentEventLog.payload.like(f'%"name": "{name}"%'))
    return and_(AgentEventLog.item_key.like("tc:%"), or_(*conditions))


def _payload(raw: str) -> dict:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _clip(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"
