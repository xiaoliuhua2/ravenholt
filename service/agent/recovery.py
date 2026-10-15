from logger import get_logger
from middleware.auth import AuthUser
from service.agent import sessions as agent_sessions
from service.system_user.users import query_system_user_by_id
from service.work_project.projects import can_run_work_project_session


logger = get_logger(__name__)


async def recover_pending_sessions() -> None:
    """启动恢复：把上个进程中断的会话收敛到确定状态。

    strix 单轨的回合由进程内的 run loop 承载，进程重启后无法续跑；这里只负责把
    没有任何在途工作的会话标记为停止，仍在途的会话保持原状交由后续清理。
    """
    pending = await agent_sessions.list_running_sessions()
    if not pending:
        return
    for session in pending:
        if not await agent_sessions.has_outstanding_session_work(session.session_id):
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="Agent runtime was interrupted by backend restart.",
            )
            continue
        user = await query_system_user_by_id(session.owner_id)
        if user is None:
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="Agent session owner no longer exists.",
            )
            continue
        auth_user = AuthUser(id=user.id, role=user.role, email=user.email, username=user.username)
        if not await can_run_work_project_session(session.session_id, auth_user.id, auth_user.role):
            await agent_sessions.force_mark_session_stopped(
                session.session_id,
                error="WorkProject is canceled.",
            )
            continue
