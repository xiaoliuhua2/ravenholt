from core.runtime.context import AgentRuntimeContext, AgentUserContext, main_agent_instance_id
from core.runtime.input_items import display_text_from_content
from core.runtime.session import get_agent_pool
from logger import get_logger
from middleware.auth import AuthUser
from schema.agent.events import AgentEventSchema, AgentInputPart
from service.agent import sessions as agent_sessions
from service.work_project.projects import can_run_work_project_session, work_project_type_for_project


logger = get_logger(__name__)


class SessionNotRunnableError(PermissionError):
    pass


class SessionBusyError(RuntimeError):
    pass


class AgentUnavailableError(ValueError):
    pass


async def submit_strix_turn(
    *,
    session_id: str,
    task: str = "",
    content: list[AgentInputPart] | None = None,
    user: AuthUser,
    requested_agent_code: str | None = None,
) -> list[AgentEventSchema]:
    """以 ravenholt 运行时为执行后端驱动一次任务（动态派生 agent 树）。

    由 root 在运行时经 ``create_agent`` 派生子代理；事件（子代理图 + 工具调用）经
    事件总线投影，操作台可见。

    ``content`` 里若含图片，会在**沙箱就绪之后**由运行时落进容器（保真通道）并做一次
    逐字转写（提示通道）——沙箱由运行时按会话自动 provision，所以落盘必须推迟到容器
    可用之后，详见 ``core.runtime.session.AgentSession._build_task_with_attachments``。
    """
    if not await agent_sessions.can_access_session(session_id, user.id, user.role):
        raise PermissionError("agent session not found")
    if not await can_run_work_project_session(session_id, user.id, user.role):
        raise SessionNotRunnableError("work project is canceled")
    if requested_agent_code is not None and not get_agent_pool().registry.has(requested_agent_code):
        raise AgentUnavailableError("agent is not available")
    title_hint = (task or "").strip() or (display_text_from_content(content) if content else "")
    agent_code = await agent_sessions.ensure_chat_session_meta(
        session_id,
        title_hint,
        requested_agent_code,
        user_id=user.id,
        user_role=user.role,
    )
    context = await build_runtime_context(session_id, user, agent_code)
    display_text = display_text_from_content(content) if content else (task or "").strip()

    runtime = await get_agent_pool().get_or_create(session_id)
    if runtime.is_running():
        raise SessionBusyError("session is already running a turn")
    return await runtime.start_strix_turn(
        task,
        context,
        agent_code=agent_code,
        display_text=display_text,
        content=content,
    )


async def submit_strix_user_turn(
    *,
    session_id: str,
    task: str = "",
    content: list[AgentInputPart] | None = None,
    user: AuthUser,
    requested_agent_code: str | None,
) -> list[AgentEventSchema]:
    """strix 轨道的回合入口：沙箱由运行时按会话自动 provision，这里直接驱动一次 run。"""
    return await submit_strix_turn(
        session_id=session_id,
        task=task,
        content=content,
        user=user,
        requested_agent_code=requested_agent_code,
    )


async def submit_new_strix_turn(
    *,
    task: str = "",
    content: list[AgentInputPart] | None = None,
    user: AuthUser,
    requested_agent_code: str | None,
) -> tuple[str, list[AgentEventSchema]]:
    """建会话并立刻跑一次 strix 回合。"""
    session_id = await agent_sessions.create_session(user_id=user.id)
    try:
        events = await submit_strix_user_turn(
            session_id=session_id,
            task=task,
            content=content,
            user=user,
            requested_agent_code=requested_agent_code,
        )
    except Exception:
        await agent_sessions.delete_session(
            session_id,
            user_id=user.id,
            user_role=user.role,
        )
        raise
    return session_id, events


async def interrupt_turn(*, session_id: str, user: AuthUser) -> list[AgentEventSchema]:
    await _raise_unless_can_access(session_id, user)
    return await get_agent_pool().try_interrupt(session_id)


async def cancel_all_tasks(*, session_id: str, user: AuthUser) -> list[AgentEventSchema]:
    await _raise_unless_can_access(session_id, user)
    return await get_agent_pool().cancel_all(session_id)


async def _raise_unless_can_access(session_id: str, user: AuthUser) -> None:
    if not await agent_sessions.can_access_session(session_id, user.id, user.role):
        raise PermissionError("agent session not found")


async def build_runtime_context(
    session_id: str,
    user: AuthUser,
    agent_code: str = "",
) -> AgentRuntimeContext:
    """构建回合运行时上下文。

    沙箱不再由前端指定：运行时在回合开始后自动 provision，因此上下文里不带容器信息，
    容器归属由 provision 结果回写会话（``update_session_runtime_sandbox``）。
    """
    work_project_id = await agent_sessions.project_id_for_session(session_id)
    # 项目类型在这里落到上下文，供运行时选作战规程（黑盒渗透 / 白盒源码审计）。
    work_project_type = (
        await work_project_type_for_project(work_project_id)
        if work_project_id is not None
        else None
    )
    return AgentRuntimeContext(
        session_id=session_id,
        user=_agent_user_context(user),
        agent_code=agent_code,
        agent_instance_id=main_agent_instance_id(session_id, user.id, agent_code) if agent_code else "",
        work_project_id=work_project_id,
        work_project_type=work_project_type,
    )


def _agent_user_context(user: AuthUser) -> AgentUserContext:
    return AgentUserContext(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )
