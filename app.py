from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# ── 兼容补丁：必须在 agents 导入之前执行 ──
# 新版 openai 把 InputTokensDetails.cached_tokens 改成了 cache_write_tokens（必填），
# 但 openai-agents SDK 还在用 cached_tokens=0，导致 pydantic 校验失败。
# 这里通过继承将 cache_write_tokens 设为可选（默认 0），让 SDK 的 lambda 能正常创建。
try:
    import openai.types.responses.response_usage as _ocu
    class _PatchedInputTokensDetails(_ocu.InputTokensDetails):
        cache_write_tokens: int = 0
    _ocu.InputTokensDetails = _PatchedInputTokensDetails
except Exception:
    pass

from agents import set_tracing_disabled
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import ROOT_PATH, get_config

from core.delegation.subagents import start_subagent_runtime, stop_subagent_runtime
from core.policy import load_policy
from core.runtime.session import get_agent_pool
from database import close_engine, create_all_tables, init_engine
from logger import get_logger
from middleware.auth import JwtAuthMiddleware
from middleware.response import (
    CommonResponseStatusMiddleware,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from router.agent.agents import router as agent_router
from router.agent.sessions import router as agent_session_router
from router.audit.events import router as audit_router
from router.blackboard.nodes import router as blackboard_router
from router.common.fallback import api_not_found_router
from router.egress_proxy.proxies import router as egress_proxy_router
from router.host.hosts import router as host_router
from router.policy.confirmations import router as policy_confirmation_router
from router.policy.policy import router as policy_router
from router.sandbox.containers import router as sandbox_container_router
from router.sandbox.images import router as sandbox_image_router
from router.system_config.config import router as system_config_router
from router.system_user.users import router as system_user_router
from router.work_project.projects import router as work_project_router
from router.work_project.source_uploads import router as work_project_source_router
from schema.system_user.users import SystemUserRole
from service.agent.event_log import settle_stale_running_subagent_events
from service.agent.recovery import recover_pending_sessions
from service.host.hosts import ensure_local_managed_host
from service.sandbox.status import (
    start_sandbox_container_status_monitor,
    stop_sandbox_container_status_monitor,
)
from service.system_user.users import create_system_user, query_system_user_by_username
from utils.urllib3_compat import install_urllib3_closed_file_close_patch


logger = get_logger(__name__)

install_urllib3_closed_file_close_patch()

WEB_DIST_PATH = ROOT_PATH / "web" / "dist-app"
API_PREFIX = "/api"


async def _bootstrap_admin_user() -> None:
    bootstrap = get_config().system.bootstrap_admin
    if not bootstrap.enabled:
        logger.debug("bootstrap admin user skipped")
        return

    if await query_system_user_by_username(bootstrap.username) is not None:
        logger.debug("bootstrap admin user already exists: %s", bootstrap.username)
        return

    await create_system_user(
        username=bootstrap.username,
        password=bootstrap.password,
        email=bootstrap.email,
        role=SystemUserRole.ADMIN,
    )
    logger.info("bootstrap admin user created: %s", bootstrap.username)





def _mount_frontend(app: FastAPI) -> None:
    """serve built frontend assets when web/dist-app exists"""
    index_path = WEB_DIST_PATH / "index.html"
    if not index_path.is_file():
        logger.debug("frontend static route skipped: %s not found", index_path)
        return

    assets_path = WEB_DIST_PATH / "assets"
    if assets_path.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_path), name="web-assets")

    async def serve_frontend(path: str = "") -> FileResponse:
        return FileResponse(index_path)

    app.add_api_route("/", serve_frontend, methods=["GET"], include_in_schema=False)
    app.add_api_route("/{path:path}", serve_frontend, methods=["GET"], include_in_schema=False)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    try:
        init_engine()
        await create_all_tables()
        await _bootstrap_admin_user()
        # 沙箱容器记录需要宿主外键：保证本机（DEFAULT_LOCAL_HOST_ID）记录存在，
        # 否则 strix 自动建容器后的记录回写、以及管理员手工建沙箱都会因宿主缺失失败。
        await ensure_local_managed_host()
        # fail-closed：红线策略不可用（缺失/解析失败/校验失败/Tier-1 被关闭）则拒绝启动
        load_policy()

        set_tracing_disabled(True)
        await start_subagent_runtime()
        # settle subagent frames stranded by a hard kill before anything can
        # re-drive a session (recovery below may legitimately emit new ones)
        await settle_stale_running_subagent_events()
        # 挂起等待审批的协程已随上次进程退出消失：把残留的待批准记录置为拒绝，
        # 否则「策略审批」页会长期显示永远等不到的条目，且会被后续请求复用。
        from service.policy.confirmations import settle_stale_pending_confirmations

        await settle_stale_pending_confirmations()
        await recover_pending_sessions()
        await get_agent_pool().start()
        await start_sandbox_container_status_monitor()

        yield
    except Exception:
        # surface startup failures; the finally block below would otherwise hide them
        logger.exception("lifespan startup failed")
        raise
    finally:
        await stop_sandbox_container_status_monitor()
        await stop_subagent_runtime()
        await get_agent_pool().stop()
        await close_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ravenholt RedTeam Agent - 开源红队多智能体协作平台，用于授权安全评估、代码审计、渗透测试与安全研究。",
        version="0.2.1",
        lifespan=lifespan,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    logger.debug("exception handlers added")

    app.add_middleware(CommonResponseStatusMiddleware)
    app.add_middleware(JwtAuthMiddleware)
    logger.debug("middleware added")

    app.include_router(system_user_router, prefix=API_PREFIX)
    app.include_router(host_router, prefix=API_PREFIX)
    app.include_router(egress_proxy_router, prefix=API_PREFIX)
    app.include_router(sandbox_image_router, prefix=API_PREFIX)
    app.include_router(sandbox_container_router, prefix=API_PREFIX)
    app.include_router(work_project_router, prefix=API_PREFIX)
    app.include_router(work_project_source_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(agent_session_router, prefix=API_PREFIX)
    app.include_router(blackboard_router, prefix=API_PREFIX)
    app.include_router(system_config_router, prefix=API_PREFIX)
    app.include_router(policy_router, prefix=API_PREFIX)
    app.include_router(policy_confirmation_router, prefix=API_PREFIX)
    app.include_router(audit_router, prefix=API_PREFIX)
    app.include_router(api_not_found_router, prefix=API_PREFIX)
    logger.debug("api router added")

    _mount_frontend(app)
    return app
