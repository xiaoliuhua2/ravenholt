from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import AgentConfig, AgentPoolConfig, AgentRuntimeConfig, IntegrationsConfig


class InstanceConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    agent_pool: AgentPoolConfig = Field(default_factory=AgentPoolConfig)
    agent_runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    @model_validator(mode="after")
    def validate_agent_codes(self):
        for code, agent in self.agents.items():
            if agent.code != code:
                raise ValueError(f"agent code mismatch: {code}")
        return self


class UpdateAgentConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=128)
    description: str
    base_url: str
    api_key: str
    model: str
    use_responses: bool
    context_window: int = Field(ge=0)


class UpdateIntegrationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_search_provider: Literal["auto", "exa", "perplexity", "searxng", "deepseek"]
    exa_api_key: str = Field(max_length=4096)
    perplexity_api_key: str = Field(max_length=4096)
    # DeepSeek 官方 Search/Fetch 接口的密钥（检索与页面抓取共用）。
    # 留空表示「跟随模型配置里已填的 DeepSeek key」——读取配置时会自动回填后再展示。
    deepseek_api_key: str = Field(default="", max_length=4096)
    searxng_base_url: str = Field(default="", max_length=1024)
    searxng_auto_provision: bool = True
    # 「通用引擎」开关：打开后平台改写 SearXNG 配置（Google/Bing/DuckDuckGo/Brave）并重启容器。
    searxng_general_engines: bool = False
    # 下面两项在控制台没有编辑入口，但**读取接口会返回它们**，而「快捷导入」是把
    # GET /instance 的 integrations 原样回传的；若请求体不接受这两个字段，
    # pydantic 的 extra="forbid" 会直接 422（表现为「批量导入 · request validation failed」）。
    # 更新语义：仅当传入非空值时才写回，避免把配置里的默认值清空。
    deepseek_base_url: str = Field(default="", max_length=1024)
    searxng_bind_addr: str = Field(default="", max_length=64)


class UpdateInstanceConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: dict[str, UpdateAgentConfigRequest]
    agent_pool: AgentPoolConfig
    agent_runtime: AgentRuntimeConfig
    integrations: UpdateIntegrationsRequest


class UpdateInstanceConfigResponse(BaseModel):
    config: InstanceConfigSchema
    restarted: bool


class FetchUpstreamModelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=4096)


class FetchUpstreamModelsResponse(BaseModel):
    models: list[str]


class CheckSearchProvidersRequest(BaseModel):
    """校验联网检索各 provider 的配置是否可用（不落盘，仅测试）。"""

    model_config = ConfigDict(extra="forbid")

    exa_api_key: str = Field(default="", max_length=4096)
    perplexity_api_key: str = Field(default="", max_length=4096)
    deepseek_api_key: str = Field(default="", max_length=4096)
    searxng_base_url: str = Field(default="", max_length=1024)
    # DeepSeek 检索走官方 /v1/tools/search，base 可自定义（例如自建网关）。
    deepseek_base_url: str = Field(default="", max_length=1024)


class SearchProviderCheckSchema(BaseModel):
    """单个 provider 的检查结果。"""

    provider: Literal["searxng", "exa", "perplexity", "deepseek"]
    # 是否已配置（未配置的 provider 不计为失败，只是不可用）
    configured: bool
    ok: bool
    # 人读的一行结论，例如「密钥有效」「未配置密钥」「HTTP 401：密钥无效」
    detail: str
    elapsed_ms: int
    http_status: int | None = None


class CheckSearchProvidersResponse(BaseModel):
    results: list[SearchProviderCheckSchema]
    # auto 模式实际会选中的 provider（按 Exa → SearXNG → Perplexity 的既有优先级取第一个可用）
    recommended: str | None = None

