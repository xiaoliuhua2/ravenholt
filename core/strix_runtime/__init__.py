"""ravenholt 运行时接缝层。

把 vendor 进 ravenholt 的运行时引擎（``AgentCoordinator`` + ``run_agent_loop`` +
``agents_graph`` 工具族）装配成 ravenholt 可调用的执行后端。

**只有一条轨道**：agent 就是 strix 原生的 ``SandboxAgent``（``build_agent``）——
一个 root 智能体，自己用 ``create_agent`` 派生 / 回收子智能体，自己用 SDK 的
``Shell`` / ``Filesystem`` 能力操作沙箱。ravenholt 一一侧只做三件事：

- 用 ravenholt 的 per-agent 国产模型配置替掉 strix 自己的 settings/model 解析；
- 把 ``sandbox_provision`` 建好的沙箱会话绑进 ``RunConfig.sandbox``，并把容器内
  Caido 句柄放进运行上下文（6 个代理工具靠它工作）；
- 挂 ravenholt 自己的东西：src-hunt 作战规程、红线闸口、事件投影、finding 镜像、
  证据工具与技能路由。

设计约束：
- 本模块只做「装配 / 适配」，不修改 ``strix`` 包内的运行时逻辑，保证后续可随上游更新。
- 运行上下文（context）沿用 ravenholt 原生 dict 形态，键与图工具族约定一致：
  ``coordinator`` / ``agent_id`` / ``parent_id`` / ``interactive`` / ``spawn_child_agent``。
- 模型由 ravenholt 侧注入（``build_configured_model`` 或任意 SDK ``Model``），
  不依赖 ravenholt 的 LiteLLM 配置，从而复用 ravenholt 的 per-agent 国产模型配置。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import Agent, Model, ModelSettings, RunConfig
from agents.sandbox import SandboxRunConfig

from core.strix_runtime.evidence_tools import EVIDENCE_TOOLS
from core.strix_runtime.prompts import with_preset_skills
from core.strix_runtime.skill_routes import SKILL_ROUTE_TOOLS
from strix.agents.factory import build_strix_agent
from strix.core.agents import AgentCoordinator
from strix.core.execution import run_agent_loop
from strix.core.execution import spawn_child_agent as strix_spawn_child_agent
from strix.core.sessions import open_agent_session
from strix.tools.finish.tool import finish_scan
from strix.tools.wait_for_user.tool import wait_for_user


if TYPE_CHECKING:
    from core.strix_runtime.projection import StrixEventProjector


logger = logging.getLogger(__name__)

_DEFAULT_ROOT_INSTRUCTIONS = (
    "You are the root agent of an autonomous security assessment run.\n"
    "Decompose the objective into focused subtasks and hand them to child agents "
    "via `create_agent`; each child reports back through `agent_finish`, whose "
    "completion report lands in your inbox. Use `wait_for_agents` to block on "
    "children, and call `finish_scan` when the assessment is complete."
)

_DEFAULT_CHILD_INSTRUCTIONS = (
    "You are a specialist child agent working in parallel with your peers.\n"
    "Stay inside the scope you were handed, finish the assigned task, and post a "
    "completion report to your parent with `agent_finish` when done. Do not call "
    "`finish_scan` — that tool belongs to the root agent."
)


def build_configured_model(agent_code: str, *, session_id: str = "") -> Model:
    """用 ravenholt 的 per-agent 配置构建 SDK 模型（复用国产模型 base_url/api_key）。

    ``session_id`` 提供时额外包一层 :class:`LlmCaptureModel`，把每次 LLM 调用的
    请求 / 响应**原文**写入旁路归档（受 ``archive.capture_llm_bodies`` 开关控制）。
    该包裹发生在 ravenholt 装配层：strix 自己的模型遥测链对显式传入的模型不生效，
    因此这里是唯一能拿到原文的位置。
    """
    from config import get_config
    from core.agent.models import build_openai_model

    cfg = get_config().agents.get(agent_code)
    if cfg is None:
        raise ValueError(f"agent config missing for code: {agent_code}")
    model: Model = build_openai_model(cfg)
    if session_id and get_config().archive.capture_llm_bodies:
        from core.strix_runtime.llm_capture import LlmCaptureModel

        model = LlmCaptureModel(
            model,
            session_id=session_id,
            model_name=cfg.model,
            provider="openai",
            base_url=cfg.base_url or None,
        )
    return model


def build_agent(
    *,
    name: str,
    model: Model,
    is_root: bool,
    instructions: str,
    extra_tools: tuple[Any, ...] = (),
    finish_tool: Any = finish_scan,
    interactive: bool = False,
    chat_completions_tools: bool = True,
    strict_tool_schemas: bool = False,
) -> Agent:
    """构建 strix 原生 ``SandboxAgent``（挂 ``Filesystem`` / ``Shell`` 能力）。

    能力工具由 SDK 在运行时按 ``RunConfig(sandbox=SandboxRunConfig(session=...))``
    注入到会话上，因此拿到持久可交互 shell、结构化文件工具与容器内 Caido 抓包工具。

    ``build_strix_agent`` 不接受 model 参数（``strix/agents/factory.py`` 固定 ``model=None``），
    因此构造后显式赋 ``model``，并补回 ``model_settings`` —— dataclass 的 ``__post_init__``
    不会重跑，不补就会丢掉「并行工具调用」的约束。

    ``chat_completions_tools`` / ``strict_tool_schemas`` 默认按 ravenholt 的国产
    OpenAI 兼容端点取最保守组合（自定义工具包成 function tool、不启用 strict schema），
    避免端点拒收 strict 工具导致整轮失败。

    ``wait_for_user`` 只在 ``interactive`` 回合由 strix 自己注册（``strix/agents/factory.py``
    的 ``if interactive: agent_tools.append(wait_for_user)``），但模型会从 ``wait_for_agents`` 的
    工具描述里得知它存在、并在「需要用户输入」时调用它 —— 未注册会直接抛
    ``ModelBehaviorError`` 把整轮打成 failed。因此非交互时这里显式补上：该工具自带
    「没有用户在线，继续干活」的友好降级（``strix/tools/wait_for_user/tool.py``），
    把「崩溃」变成「可恢复」。interactive 时由 factory 注册，这里不重复挂（会重名冲突）。
    """
    tools = extra_tools if interactive else (*extra_tools, wait_for_user)
    agent = build_strix_agent(
        name=name,
        is_root=is_root,
        instructions_override=instructions,
        extra_tools=tools,
        interactive=interactive,
        finish_tool=finish_tool,
        chat_completions_tools=chat_completions_tools,
        strict_tool_schemas=strict_tool_schemas,
    )
    agent.model = model
    agent.model_settings = ModelSettings(parallel_tool_calls=False)
    return agent


@dataclass(slots=True)
class StrixRunResult:
    """一次 ravenholt 运行时 runs 的结果快照（agent 图 + 终稿输出）。"""

    root_id: str
    statuses: dict[str, Any] = field(default_factory=dict)
    parent_of: dict[str, Any] = field(default_factory=dict)
    names: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, Any] = field(default_factory=dict)
    final_output: Any = None

    @property
    def agent_count(self) -> int:
        return len(self.statuses)


async def run_strix_session(
    *,
    task: str,
    model: Model,
    sandbox_session: Any,
    caido_client: Any,
    child_model: Model | Callable[[str], Model] | None = None,
    instructions: str | None = None,
    child_instructions: str | None = None,
    root_finish_tool: Any = finish_scan,
    interactive: bool = False,
    max_turns: int = 100,
    agents_db_path: Path,
    work_project_id: int | None = None,
    session_id: str = "",
    event_sink: Callable[[str, Any], None] | None = None,
    projector: "StrixEventProjector | None" = None,
    root_id: str = "root",
    root_name: str = "Root Agent",
    extra_context: dict[str, Any] | None = None,
    chat_completions_tools: bool = True,
    strict_tool_schemas: bool = False,
) -> StrixRunResult:
    """用 ravenholt 运行时驱动一次会话：注册 root、注入 spawner 闭包、跑 run loop。

    ``sandbox_session`` / ``caido_client`` 是**必传**的：沙箱由
    ``core.strix_runtime.sandbox_provision.provision_sandbox`` 事先建好并包上红线闸口，
    没有沙箱就不该跑渗透回合（调用方负责在提供失败时终止，而不是降级跑空壳）。

    ``child_model`` 可为单个 ``Model``（所有子代理共用）或工厂 ``name -> Model``
    （每个子代理独立实例，便于测试脚本化）。缺省回退到 root 的 ``model``。

    ``projector`` 提供时，SDK 流事件与协调器图状态会投影到 ravenholt 事件总线
    （见 ``core.strix_runtime.projection``）；显式传入的 ``event_sink`` 优先。
    """
    coordinator = AgentCoordinator()
    coordinator.root_finish_tool = getattr(root_finish_tool, "name", "finish_scan")

    if projector is not None and event_sink is None:
        event_sink = projector.on_stream_event

    sessions_to_close: list[Any] = []

    # 把沙箱会话绑进 RunConfig：SDK 的 Filesystem/Shell 能力据此挂到该会话上；
    # 代理工具从运行上下文取 ``caido_client``（strix/tools/proxy/tools.py:_ctx_client）。
    run_config = RunConfig(sandbox=SandboxRunConfig(session=sandbox_session))

    # 路由工具常驻；项目绑定 → 证据工具。沙箱工具由 SDK 能力提供，不再挂 ravenholt 侧实现。
    extra_tools: tuple[Any, ...] = (
        *SKILL_ROUTE_TOOLS,
        *(EVIDENCE_TOOLS if work_project_id is not None else ()),
    )

    def _build_agent(
        *,
        name: str,
        agent_model: Model,
        is_root: bool,
        agent_instructions: str,
    ) -> Agent:
        return build_agent(
            name=name,
            model=agent_model,
            is_root=is_root,
            instructions=agent_instructions,
            extra_tools=extra_tools,
            finish_tool=root_finish_tool,
            interactive=interactive,
            chat_completions_tools=chat_completions_tools,
            strict_tool_schemas=strict_tool_schemas,
        )

    root_agent = _build_agent(
        name=root_name,
        agent_model=model,
        is_root=True,
        agent_instructions=instructions or _DEFAULT_ROOT_INSTRUCTIONS,
    )

    await coordinator.register(root_id, root_name, parent_id=None, task=task, skills=[])

    def _resolve_child_model(child_name: str) -> Model:
        if callable(child_model):
            return child_model(child_name)
        return child_model or model

    base_child_instructions = child_instructions or _DEFAULT_CHILD_INSTRUCTIONS

    def child_factory(*, name: str, skills: list[str]) -> Agent:
        return _build_agent(
            name=name,
            agent_model=_resolve_child_model(name),
            is_root=False,
            # 把 root 经 create_agent 指定的技能渲染进 child 提示（预置技能块），
            # 使「技能路由 → 子代理」真正生效（strix 侧 factory(skills=...) 只做透传）。
            agent_instructions=with_preset_skills(base_child_instructions, skills),
        )

    async def spawn_child(**kwargs: Any) -> dict[str, Any]:
        return await strix_spawn_child_agent(
            coordinator=coordinator,
            factory=child_factory,
            agents_db_path=agents_db_path,
            sessions_to_close=sessions_to_close,
            run_config=run_config,
            max_turns=max_turns,
            interactive=interactive,
            event_sink=event_sink,
            hooks=None,
            **kwargs,
        )

    context: dict[str, Any] = {
        "coordinator": coordinator,
        "agent_id": root_id,
        "parent_id": None,
        "interactive": interactive,
        "spawn_child_agent": spawn_child,
        "sandbox_session": sandbox_session,
        "caido_client": caido_client,
        "work_project_id": work_project_id,
        "session_id": session_id,
    }
    if extra_context:
        context.update(extra_context)

    root_session = open_agent_session(root_id, agents_db_path)
    sessions_to_close.append(root_session)
    await coordinator.attach_runtime(root_id, session=root_session, resumable=interactive)

    watcher: asyncio.Task[None] | None = None
    if projector is not None:
        watcher = asyncio.create_task(
            projector.watch_graph(coordinator), name=f"strix-graph-{root_id}"
        )

    result: Any = None
    try:
        result = await run_agent_loop(
            agent=root_agent,
            initial_input=task,
            run_config=run_config,
            context=context,
            max_turns=max_turns,
            coordinator=coordinator,
            agent_id=root_id,
            interactive=interactive,
            session=root_session,
            event_sink=event_sink,
        )
    finally:
        if projector is not None:
            # 最终状态兜底：run 结束前再投影一次，保证终态（completed/failed）不丢。
            try:
                await projector.emit_graph_delta(coordinator)
            except Exception:  # noqa: BLE001 - 投影失败不得影响收尾
                logger.exception("final strix graph projection failed")
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
        # 仍在活动（running/waiting/budget_paused）的子代理先落终态、再取消其任务：
        # 子代理任务被 cancel 抛的是 CancelledError（BaseException），运行循环里的
        # `except Exception` 兜不住，状态会永远停在 running——表现为「任务已结束但
        # 子智能体一直显示 running」，刷新后依旧。
        for agent in await coordinator.active_agents_except(root_id):
            await coordinator.request_stop(agent["agent_id"])
        await coordinator.cancel_descendants(root_id)
        if projector is not None:
            try:
                await projector.emit_graph_delta(coordinator)
            except Exception:  # noqa: BLE001 - 投影失败不得影响收尾
                logger.exception("final strix graph settle projection failed")
        for session in sessions_to_close:
            try:
                closed = session.close()
                if inspect.isawaitable(closed):
                    await closed
            except Exception:  # noqa: BLE001 - teardown must not mask the run result
                logger.exception("closing strix agent session failed")

    parent_of, statuses, names, errors = await coordinator.graph_snapshot()
    return StrixRunResult(
        root_id=root_id,
        statuses=statuses,
        parent_of=parent_of,
        names=names,
        errors=errors,
        final_output=getattr(result, "final_output", None),
    )


__all__ = [
    "StrixRunResult",
    "build_agent",
    "build_configured_model",
    "run_strix_session",
]
