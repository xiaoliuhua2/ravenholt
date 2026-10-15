import json
import secrets
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT_PATH = Path(__file__).resolve().parent
WORKSPACE = ROOT_PATH / ".ravenholt"
CONFIG_FILE = WORKSPACE / "config.json"


# strict type config base model
class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# system config
class BootstrapAdminConfig(StrictConfigModel):
    enabled: bool = Field(default=False)
    username: str = Field(default="admin", min_length=1, max_length=64)
    email: str = Field(default="admin@ravenholt.local", min_length=1, max_length=255)
    password: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_password_when_enabled(self):
        if self.enabled and not self.password:
            raise ValueError("bootstrap admin password is required when bootstrap admin is enabled")
        return self


class SystemConfig(StrictConfigModel):
    listen_addr: str = Field(default="127.0.0.1")
    listen_port: int = Field(default=8000)
    encrypt_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32), min_length=32)
    bootstrap_admin: BootstrapAdminConfig = Field(default_factory=BootstrapAdminConfig)


# database config
class DatabaseConfig(StrictConfigModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5432)
    database: str = Field(default="ravenholt")
    username: str = Field(default="")
    password: str = Field(default="")
    pool_size: int = Field(default=32)
    max_overflow: int = Field(default=32)
    pool_timeout_seconds: int = Field(default=30)
    pool_recycle_seconds: int = Field(default=1800)
    pool_pre_ping: bool = Field(default=True)


# agent config
class AgentConfig(StrictConfigModel):
    code: str = Field(default="")
    name: str = Field(default="")
    description: str = Field(default="")
    base_url: str = Field(default="")
    api_key: str = Field(default="")
    model: str = Field(default="")
    use_responses: bool = Field(default=False)
    context_window: int = Field(default=1000000, ge=0)


# per-process agent runtime pool tuning
class AgentPoolConfig(StrictConfigModel):
    max_size: int = Field(default=256, ge=1)
    ttl_seconds: int = Field(default=30 * 60, ge=0)
    sweep_interval_seconds: int = Field(default=60, ge=1)


# per-process agent run tuning
class AgentRuntimeConfig(StrictConfigModel):
    main_max_turns: int = Field(default=1000, ge=1)
    subordinate_max_turns: int = Field(default=1000, ge=1)
    model_stream_idle_timeout_seconds: int = Field(default=600, ge=30)
    context_compression_enabled: bool = True
    context_compression_trigger_ratio: float = Field(default=0.90, gt=0, lt=1)
    context_compression_hard_stop_ratio: float = Field(default=0.98, gt=0, lt=1)
    context_compression_target_ratio: float = Field(default=0.20, gt=0, lt=1)
    context_budget_model_call_ratio: float = Field(default=0.80, gt=0, lt=1)
    context_compression_preserve_recent_ratio: float = Field(default=0.25, gt=0, lt=1)
    context_compression_preserve_recent_items: int = Field(default=20, ge=1)
    context_compression_min_items: int = Field(default=12, ge=1)
    context_compression_summary_max_tokens: int = Field(default=8000, ge=512)


# sandbox config
class SandboxConfig(StrictConfigModel):
    # 沙箱容器接入的自定义 docker 网络名。为空时沿用 strix 默认 bridge + 端口发布；
    # 指向一个**部署者预先建好**的网络（如 macvlan）时，容器获得局域网内独立 IP，
    # 目标可主动回连。网段 / 网关 / 宿主侧可达性由部署者按其环境自行决定，这里只记录
    # 网络名，不硬编码任何网段。
    network: str = Field(default="")


# 旁路归档器配置：把事件总线上的**全量原始事件** append-only 落盘。
#
# 为什么需要：REST ``/agent-sessions/{sid}/events`` 只回放 ``is_persistable`` 的事件
# （见 ``core.runtime.timeline``），逐字思考 / 正文增量、运行状态切换等帧从不落库，
# 因此任何「轮询快照式」的外部监控都拿不到逐字过程。归档器在事件出口处旁路写全量帧，
# 是外部聚合器唯一能拿到「全部过程」的位置。
#
# 体积：增量帧（delta）是主体，按小时分片 + 保留期回收 + 冷数据可 gzip。归档失败一律
# 静默降级，绝不阻断主流程（用户仍看得到实时输出）。
class ArchiveConfig(StrictConfigModel):
    enabled: bool = Field(default=True)
    # 是否归档逐字增量帧（关闭可显著减小体积，但监控器将失去逐字过程）
    capture_deltas: bool = Field(default=True)
    capture_text_delta: bool = Field(default=True)
    capture_thinking_delta: bool = Field(default=True)
    # 是否归档 LLM 请求/响应**原文**（装配层包裹模型捕获；体积最大，可按需关闭）
    capture_llm_bodies: bool = Field(default=True)
    # 单条 LLM 原文的最大字符数，超出截断并标记 truncated
    llm_body_max_chars: int = Field(default=524288, ge=4096)
    # 归档保留天数；0 表示永久保留
    retention_days: int = Field(default=7, ge=0)
    # 归档写队列上限；积压超过则丢弃并计数（宁可丢归档，不可拖垮主流程）
    queue_max: int = Field(default=200000, ge=1000)


# 联网检索（strix ``web_search`` / ``web_get_contents``）的 provider 与密钥。
# provider=auto：有 Exa 用 Exa，否则用 Perplexity；两者都空则该工具返回「未配置」，
# agent 会自行降级为「靠自身知识与实验」。密钥在启动时经环境变量注入 strix。
class IntegrationsConfig(StrictConfigModel):
    web_search_provider: Literal["auto", "exa", "perplexity", "searxng"] = Field(default="auto")
    exa_api_key: str = Field(default="")
    perplexity_api_key: str = Field(default="")
    # 自建 SearXNG 的 base URL（provider=searxng 时使用；无需 API key）。
    # 默认指向本机容器，做到「零配置即可联网检索」——部署者不必在控制台填任何东西；
    # 平台启动时会 best-effort 保障该容器在跑（见 core/searxng_provision.py）。
    searxng_base_url: str = Field(default="http://127.0.0.1:8888")
    # 是否允许平台在本机 SearXNG 不可达时**自动拉起容器**
    # （存在就 docker start，不存在就 docker run；见 core/searxng_provision.py）。
    # 默认开；若部署环境不允许平台执行 docker 操作，可在控制台关掉。
    # 环境变量 RAVENHOLT_SEARXNG_AUTOPROVISION=0 可强制关闭（优先级更高）。
    searxng_auto_provision: bool = Field(default=True)


# global config
class GlobalConfig(StrictConfigModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    agent_pool: AgentPoolConfig = Field(default_factory=AgentPoolConfig)
    agent_runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)


###
# global config instance
###
_cfg: GlobalConfig = GlobalConfig()
_LEGACY_CONTEXT_COMPRESSION_TRIGGER_RATIO = 0.95


def load_config():
    """load config from json file"""
    global _cfg

    next_cfg = read_config_file()
    for field_name in type(_cfg).model_fields:
        setattr(_cfg, field_name, getattr(next_cfg, field_name))


def get_config():
    """get config instance"""
    global _cfg
    return _cfg


def sync_strix_llm_env() -> None:
    """把当前预设的模型配置写入 strix 期望的环境变量，覆盖其自带的配置来源。

    strix 的内部 LLM 调用（漏洞去重、上下文压缩等）走 ``StrixProvider`` →
    ``load_settings()``，其优先级为「环境变量 > ~/.strix/cli-config.json > 默认值」。
    ravenholt 此前只给主 agent 的 Model 实例注入过配置，没覆盖这条路径，导致 strix
    的内部调用会拿到 HOME 目录里遗留的旧 key（表现为 401 Authentication Fails）。
    这里把默认预设同步进环境变量，使 strix 全局跟随 ravenholt 的配置。

    必须在 strix 首次 ``load_settings()`` 之前调用（该函数带记忆化缓存，首次解析后
    不会再读环境变量）。
    """
    import os

    agents = _cfg.agents
    agent: AgentConfig | None = agents.get("cso") or next(
        (item for item in agents.values() if item.api_key), None
    )
    if agent is None or not agent.api_key:
        return

    os.environ["LLM_API_KEY"] = agent.api_key
    if agent.base_url:
        os.environ["LLM_API_BASE"] = agent.base_url
    if agent.model:
        os.environ["STRIX_LLM"] = f"{_litellm_provider(agent.base_url)}/{agent.model}"


def _litellm_provider(base_url: str) -> str:
    """从 base_url 推断 LiteLLM 的 provider 前缀（未知时按 OpenAI 兼容端点处理）。"""
    return "deepseek" if "deepseek" in base_url.lower() else "openai"


def sync_strix_sandbox_env() -> None:
    """把配置的沙箱网络名注入 strix 读取的环境变量。

    strix 的 docker backend 在建容器时读 ``STRIX_DOCKER_SANDBOX_NETWORK``
    （``strix/runtime/docker_client.py``）：有值时把沙箱挂到该网络并放弃端口发布
    （容器改用网络内 IP），无值时沿用默认 bridge + 端口发布。该变量在建容器时按需
    读取，进程启动时注入一次即可覆盖后续所有容器。

    只注入**非空**值 —— 保留部署者手动导出的同名环境变量被尊重的可能。
    """
    import os

    network = _cfg.sandbox.network.strip()
    if network:
        os.environ["STRIX_DOCKER_SANDBOX_NETWORK"] = network


def _set_or_clear_env(name: str, value: str) -> None:
    import os

    if value:
        os.environ[name] = value
    else:
        os.environ.pop(name, None)


def sync_strix_search_env() -> None:
    """把联网检索的 provider 与密钥注入 strix 读取的环境变量。

    strix 的 ``web_search`` / ``web_get_contents`` 走 ``load_settings().integrations``，
    优先级为「环境变量 > ~/.strix/cli-config.json > 默认值」。控制台配置经此注入，
    使工具跟随实例配置；密钥为空时清除同名变量，避免读到遗留值。

    与 ``sync_strix_llm_env`` 一样，需在 strix 首次 ``load_settings()`` 之前调用；
    运行期改动请配合 :func:`reset_strix_settings_cache` 让缓存失效。
    """
    integrations = _cfg.integrations
    _set_or_clear_env("STRIX_WEB_SEARCH_PROVIDER", integrations.web_search_provider)
    _set_or_clear_env("EXA_API_KEY", integrations.exa_api_key)
    _set_or_clear_env("PERPLEXITY_API_KEY", integrations.perplexity_api_key)
    _set_or_clear_env("STRIX_SEARXNG_BASE_URL", integrations.searxng_base_url)
    # 记一条日志便于运维核对「线上到底注入了什么」
    # （注意：/proc/<pid>/environ 不反映运行时 os.environ 变更，不能用它验证）
    try:
        from logger import get_logger

        get_logger(__name__).info(
            "联网检索已注入：provider=%s | searxng=%s | exa=%s | perplexity=%s",
            integrations.web_search_provider,
            integrations.searxng_base_url or "(空)",
            "有" if integrations.exa_api_key else "无",
            "有" if integrations.perplexity_api_key else "无",
        )
    except Exception:  # noqa: BLE001 - 日志失败不影响注入本身
        pass


def reset_strix_settings_cache() -> None:
    """让 strix 备忘化的 ``load_settings()`` 失效，使环境变量改动即时生效。"""
    try:
        from strix.config.loader import reset_settings_cache
    except Exception:  # noqa: BLE001 - strix 不可用时不影响主流程
        return
    reset_settings_cache()


def read_config_file() -> GlobalConfig:
    """read and validate config.json without mutating global state"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = _migrate_config_data(data)
    return GlobalConfig.model_validate(data)


def write_config_file(cfg: GlobalConfig) -> None:
    """atomically write a validated config.json"""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = cfg.model_dump(mode="json")
    payload = json.dumps(data, ensure_ascii=False, indent=4)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=WORKSPACE,
        prefix=".config.",
        suffix=".json.tmp",
        delete=False,
    ) as f:
        temp_path = Path(f.name)
        f.write(payload)
        f.write("\n")

    temp_path.replace(CONFIG_FILE)


def _migrate_config_data(data: dict[str, Any]) -> dict[str, Any]:
    runtime = data.get("agent_runtime")
    if not isinstance(runtime, dict):
        return data
    default_runtime = AgentRuntimeConfig()
    if "context_budget_model_call_ratio" not in runtime:
        runtime["context_budget_model_call_ratio"] = default_runtime.context_budget_model_call_ratio
    if runtime.get("context_compression_trigger_ratio") == _LEGACY_CONTEXT_COMPRESSION_TRIGGER_RATIO:
        runtime["context_compression_trigger_ratio"] = default_runtime.context_compression_trigger_ratio
    return data
