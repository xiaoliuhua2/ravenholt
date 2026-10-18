import asyncio
import time
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from config import (
    AgentConfig,
    AgentPoolConfig,
    AgentRuntimeConfig,
    GlobalConfig,
    get_config,
    read_config_file,
    reset_strix_settings_cache,
    sync_strix_search_env,
    write_config_file,
)
from core.delegation.subagents import start_subagent_runtime, stop_subagent_runtime
from core.runtime.session import AgentSessionPool, get_agent_pool, replace_agent_pool
from logger import get_logger
from schema.system_config.config import InstanceConfigSchema, UpdateInstanceConfigRequest


logger = get_logger(__name__)

_config_lock = asyncio.Lock()


@dataclass(frozen=True)
class InstanceConfigApplyResult:
    config: InstanceConfigSchema
    restarted: bool


async def get_instance_config() -> InstanceConfigApplyResult:
    async with _config_lock:
        file_cfg = read_config_file()
        return await _apply_instance_config_from_file(file_cfg)


async def update_instance_config(request: UpdateInstanceConfigRequest) -> InstanceConfigApplyResult:
    async with _config_lock:
        current = read_config_file()
        if set(request.agents) != set(current.agents):
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST.value,
                detail="agent set cannot be changed",
            )

        agents = {}
        for code, agent in current.agents.items():
            patch = request.agents[code]
            agents[code] = agent.model_copy(update={
                "name": patch.name,
                "description": patch.description,
                "base_url": patch.base_url,
                "api_key": patch.api_key,
                "model": patch.model,
                "use_responses": patch.use_responses,
                "context_window": patch.context_window,
            })

        next_cfg = current.model_copy(update={
            "agents": agents,
            "agent_pool": request.agent_pool,
            "agent_runtime": request.agent_runtime,
            "integrations": current.integrations.model_copy(update={
                "web_search_provider": request.integrations.web_search_provider,
                "exa_api_key": request.integrations.exa_api_key,
                "perplexity_api_key": request.integrations.perplexity_api_key,
                "deepseek_api_key": request.integrations.deepseek_api_key,
                "searxng_base_url": request.integrations.searxng_base_url,
                "searxng_auto_provision": request.integrations.searxng_auto_provision,
                "searxng_general_engines": request.integrations.searxng_general_engines,
            }),
        })
        write_config_file(next_cfg)
        return await _apply_instance_config_from_file(next_cfg)


_UPSTREAM_MODELS_TIMEOUT_SECONDS = 20.0


async def fetch_upstream_models(base_url: str, api_key: str) -> list[str]:
    """fetch the model id list from an OpenAI-compatible upstream vendor"""

    url = _build_models_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=_UPSTREAM_MODELS_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY.value,
            detail="连接上游模型服务超时，请检查基础 URL 是否可达",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY.value,
            detail="无法连接到上游模型服务，请检查基础 URL 是否正确",
        ) from exc

    if response.status_code in (HTTPStatus.UNAUTHORIZED.value, HTTPStatus.FORBIDDEN.value):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail=f"上游拒绝了该 API 密钥（{response.status_code}），请检查密钥是否有效",
        )
    if response.status_code == HTTPStatus.NOT_FOUND.value:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail="上游未提供 /models 接口（404），该厂商可能不兼容 OpenAI 模型列表协议",
        )
    if response.status_code >= HTTPStatus.BAD_REQUEST.value:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail=f"上游返回错误状态 {response.status_code}，无法获取模型列表",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail="上游返回内容不是合法 JSON，无法解析模型列表",
        ) from exc

    models = _extract_model_ids(payload)
    if not models:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail="上游未返回任何模型，请确认该密钥的可用模型权限",
        )
    return models


def _build_models_url(base_url: str) -> str:
    trimmed = base_url.strip().rstrip("/")
    parts = urlsplit(trimmed)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST.value,
            detail="基础 URL 必须是合法的 http(s) 地址",
        )
    if trimmed.endswith("/models"):
        return trimmed
    return f"{trimmed}/models"


def _extract_model_ids(payload: object) -> list[str]:
    raw_items: list[object]
    if isinstance(payload, dict):
        candidate = payload.get("data")
        if candidate is None:
            candidate = payload.get("models")
        raw_items = candidate if isinstance(candidate, list) else []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []

    models: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            value = item.get("id") or item.get("name") or item.get("model")
            model_id = value.strip() if isinstance(value, str) else ""
        else:
            model_id = ""
        if model_id and model_id not in seen:
            seen.add(model_id)
            models.append(model_id)
    return models


async def _sync_searxng_general_engines(enabled: bool) -> None:
    """把「SearXNG 通用引擎」开关落到容器配置（best-effort，失败只记日志）。

    只在平台托管的那份 settings.yml 上生效；状态已一致时是空操作（不会重启容器）。
    ``docker restart`` 是阻塞调用，放到线程里执行，避免卡住事件循环。
    """
    try:
        from core.searxng_provision import apply_general_engines

        ok = await asyncio.to_thread(apply_general_engines, enabled)
        logger.info("SearXNG 通用引擎开关同步完成：enabled=%s ok=%s", enabled, ok)
    except Exception:  # noqa: BLE001 - 同步失败不影响保存本身
        logger.warning("SearXNG 通用引擎开关同步失败（不影响保存）", exc_info=True)


async def _apply_instance_config_from_file(file_cfg: GlobalConfig) -> InstanceConfigApplyResult:
    previous = _snapshot_instance_config(get_config())
    general_engines_before = previous.integrations.searxng_general_engines
    runtime_changed = _apply_instance_config(file_cfg)
    if runtime_changed:
        try:
            applied_now = await rebuild_agent_instances()
        except Exception:
            _restore_instance_config(previous)
            raise
        if applied_now:
            logger.info("instance config applied and agent instances rebuilt")
        else:
            logger.info(
                "instance config applied; agent instance rebuild deferred until running turns finish"
            )
    if file_cfg.integrations.searxng_general_engines != general_engines_before:
        # 配置确实落地后再同步容器，避免重建失败回滚时白改一次 SearXNG。
        await _sync_searxng_general_engines(file_cfg.integrations.searxng_general_engines)
    return InstanceConfigApplyResult(
        config=_instance_config_from_global(get_config()),
        restarted=runtime_changed,
    )


def _apply_instance_config(file_cfg: GlobalConfig) -> bool:
    """应用实例配置；返回是否发生**运行期**（模型 / 池 / 运行参数）变更。

    ``integrations``（联网检索 provider 与密钥）单独处理：只重注入环境变量并让
    strix 的 ``load_settings`` 缓存失效，不触发 agent 实例重建。
    """
    current = get_config()
    runtime_changed = _instance_config_changed(current, file_cfg)
    integrations_changed = current.integrations != file_cfg.integrations
    if not runtime_changed and not integrations_changed:
        return False

    current.agents = _copy_agents(file_cfg.agents)
    current.agent_pool = _copy_agent_pool(file_cfg.agent_pool)
    current.agent_runtime = _copy_agent_runtime(file_cfg.agent_runtime)
    current.integrations = file_cfg.integrations.model_copy(deep=True)
    if integrations_changed:
        sync_strix_search_env()
        reset_strix_settings_cache()
    return runtime_changed


def _instance_config_changed(current: GlobalConfig, next_cfg: GlobalConfig) -> bool:
    return (
        current.agents != next_cfg.agents
        or current.agent_pool != next_cfg.agent_pool
        or current.agent_runtime != next_cfg.agent_runtime
    )


def _copy_agents(agents: dict[str, AgentConfig]) -> dict[str, AgentConfig]:
    return {code: agent.model_copy(deep=True) for code, agent in agents.items()}


def _copy_agent_pool(agent_pool: AgentPoolConfig) -> AgentPoolConfig:
    return agent_pool.model_copy(deep=True)


def _copy_agent_runtime(agent_runtime: AgentRuntimeConfig) -> AgentRuntimeConfig:
    return agent_runtime.model_copy(deep=True)


def _snapshot_instance_config(cfg: GlobalConfig) -> InstanceConfigSchema:
    return _instance_config_from_global(cfg).model_copy(deep=True)


def _restore_instance_config(snapshot: InstanceConfigSchema) -> None:
    current = get_config()
    current.agents = _copy_agents(snapshot.agents)
    current.agent_pool = _copy_agent_pool(snapshot.agent_pool)
    current.agent_runtime = _copy_agent_runtime(snapshot.agent_runtime)
    current.integrations = snapshot.integrations.model_copy(deep=True)
    sync_strix_search_env()
    reset_strix_settings_cache()


CONFIG_RELOAD_CLOSE_REASON = "instance config updated"
# 有会话正在跑时，配置重建不立即生效，避免打断正在执行的轮次；
# 最多等这么久（秒）再强制重建，防止个别会话长期挂住导致配置永不生效。
_DEFERRED_REBUILD_GRACE_SECONDS = 30 * 60
_DEFERRED_REBUILD_POLL_SECONDS = 5.0

_deferred_rebuild_task: asyncio.Task | None = None


async def rebuild_agent_instances() -> bool:
    """Rebuild agent instances without aborting in-flight turns.

    Swapping the pool closes every pooled session's event streams, so doing it
    while a turn is running would kill that turn mid-tool. When sessions are
    still working we wait for them to converge (bounded by a grace period) and
    swap afterwards; during the wait the current pool stays in place, so
    interrupt / cancel / subagent routing keep resolving to the live session.

    Returns whether the swap happened immediately.
    """
    pool = get_agent_pool()
    if pool.has_running_sessions():
        _schedule_deferred_rebuild(pool)
        return False
    await _swap_agent_pool()
    return True


def _schedule_deferred_rebuild(pool: AgentSessionPool) -> None:
    global _deferred_rebuild_task
    task = _deferred_rebuild_task
    if task is not None and not task.done():
        # 已有待办在等：它会使用最新落盘的配置，无需重复排队
        logger.info("agent instance rebuild already pending; coalesced")
        return
    _deferred_rebuild_task = asyncio.create_task(
        _deferred_rebuild(pool),
        name="agent-config-rebuild-deferred",
    )


async def _deferred_rebuild(pool: AgentSessionPool) -> None:
    deadline = time.monotonic() + _DEFERRED_REBUILD_GRACE_SECONDS
    while pool.has_running_sessions() and time.monotonic() < deadline:
        await asyncio.sleep(_DEFERRED_REBUILD_POLL_SECONDS)
    if pool.has_running_sessions():
        logger.warning(
            "agent instance rebuild waited %.0fs for running sessions; forcing rebuild",
            _DEFERRED_REBUILD_GRACE_SECONDS,
        )
    else:
        logger.info("agent instance rebuild applied after running turns finished")
    try:
        await _swap_agent_pool()
    except Exception:
        logger.exception("deferred agent instance rebuild failed")


async def _swap_agent_pool() -> None:
    old_pool = get_agent_pool()
    new_pool = replace_agent_pool(AgentSessionPool())
    try:
        try:
            await stop_subagent_runtime()
        finally:
            await old_pool.stop(reason=CONFIG_RELOAD_CLOSE_REASON)
        await start_subagent_runtime()
        await new_pool.start()
    except Exception:
        logger.exception("agent instance rebuild failed")
        await new_pool.stop()
        fallback_pool = replace_agent_pool(AgentSessionPool())
        await fallback_pool.start()
        raise


def _instance_config_from_global(cfg: GlobalConfig) -> InstanceConfigSchema:
    return InstanceConfigSchema(
        agents=cfg.agents,
        agent_pool=cfg.agent_pool,
        agent_runtime=cfg.agent_runtime,
        integrations=cfg.integrations,
    )
