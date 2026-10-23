import { Button, Spin, TabPane, Tabs } from "@douyinfe/semi-ui";
import { ChevronRight, Eraser, Eye, EyeOff, Save, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { getInstanceConfig, updateInstanceConfig, checkSearchProviders } from "../../shared/api/systemConfig";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import { cx } from "../../shared/lib/className";
import type {
  AgentConfig,
  AgentPoolConfig,
  AgentRuntimeConfig,
  CheckSearchProvidersResponse,
  InstanceConfig,
  IntegrationsConfig,
  UpdateInstanceConfigRequest,
} from "../../shared/api/types";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { QuickImportPanel, type QuickImportHandle } from "../quick-import/QuickImportPage";

type AgentFormValue = AgentConfig;

type ConfigFormValue = {
  agents: AgentFormValue[];
  agent_pool: AgentPoolConfig;
  agent_runtime: AgentRuntimeConfig;
  integrations: IntegrationsConfig;
};

// Tab 键与「未保存改动」标记的对应关系。
type ConfigTabKey = "agents" | "runtime" | "integrations" | "import";

type FieldKey<T, Value> = {
  [Key in keyof T]: T[Key] extends Value ? Key : never;
}[keyof T];

type ConfigField<T> =
  | { kind: "number"; key: FieldKey<T, number>; label: string; hint: string; unit?: string; min?: number; max?: number; step?: number }
  | { kind: "toggle"; key: FieldKey<T, boolean>; label: string; hint: string };

const DEFAULT_AGENT_POOL: AgentPoolConfig = {
  max_size: 256,
  ttl_seconds: 1800,
  sweep_interval_seconds: 60,
};

const DEFAULT_AGENT_RUNTIME: AgentRuntimeConfig = {
  main_max_turns: 1000,
  subordinate_max_turns: 1000,
  model_stream_idle_timeout_seconds: 300,
  context_compression_enabled: true,
  context_compression_trigger_ratio: 0.9,
  context_compression_hard_stop_ratio: 0.98,
  context_compression_target_ratio: 0.2,
  context_budget_model_call_ratio: 0.8,
  context_compression_preserve_recent_ratio: 0.25,
  context_compression_preserve_recent_items: 20,
  context_compression_min_items: 12,
  context_compression_summary_max_tokens: 8000,
};

const DEFAULT_INTEGRATIONS: IntegrationsConfig = {
  web_search_provider: "auto",
  exa_api_key: "",
  perplexity_api_key: "",
  deepseek_api_key: "",
  searxng_base_url: "",
  searxng_auto_provision: true,
  searxng_general_engines: false,
};

function integrationsSummary(integrations: IntegrationsConfig): string {
  const provider = integrations.web_search_provider ?? "auto";
  const hasKey = Boolean((integrations.exa_api_key ?? "").trim())
    || Boolean((integrations.perplexity_api_key ?? "").trim())
    || Boolean((integrations.searxng_base_url ?? "").trim());
  const fetchReady = Boolean((integrations.deepseek_api_key ?? "").trim());
  return `provider ${provider} · ${hasKey ? "已配置" : "未配置（检索不可用）"} · 抓取${fetchReady ? "DeepSeek 已配置" : "未配置"}`;
}

const RUNTIME_FIELDS: ConfigField<AgentRuntimeConfig>[] = [
  { kind: "number", key: "main_max_turns", label: "主最大轮次", hint: "main_max_turns", unit: "轮", min: 1 },
  { kind: "number", key: "subordinate_max_turns", label: "从属最大轮次", hint: "subordinate_max_turns", unit: "轮", min: 1 },
  { kind: "number", key: "model_stream_idle_timeout_seconds", label: "流空闲超时", hint: "model_stream_idle_timeout_seconds", unit: "秒", min: 30 },
  { kind: "number", key: "context_compression_min_items", label: "最少保留条目", hint: "context_compression_min_items", unit: "条", min: 1 },
  { kind: "number", key: "context_compression_trigger_ratio", label: "触发比例", hint: "context_compression_trigger_ratio", unit: "比例", min: 0.01, max: 0.99, step: 0.01 },
  { kind: "number", key: "context_compression_hard_stop_ratio", label: "硬停止比例", hint: "context_compression_hard_stop_ratio", unit: "比例", min: 0.01, max: 0.99, step: 0.01 },
  { kind: "number", key: "context_compression_target_ratio", label: "目标比例", hint: "context_compression_target_ratio", unit: "比例", min: 0.01, max: 0.99, step: 0.01 },
  { kind: "number", key: "context_budget_model_call_ratio", label: "模型调用预算", hint: "context_budget_model_call_ratio", unit: "比例", min: 0.01, max: 0.99, step: 0.01 },
  { kind: "number", key: "context_compression_preserve_recent_ratio", label: "保留近期比例", hint: "preserve_recent_ratio", unit: "比例", min: 0.01, max: 0.99, step: 0.01 },
  { kind: "number", key: "context_compression_preserve_recent_items", label: "保留近期条目", hint: "preserve_recent_items", unit: "条", min: 1 },
  { kind: "number", key: "context_compression_summary_max_tokens", label: "摘要最大 Token", hint: "context_compression_summary_max_tokens", unit: "token", min: 512 },
  { kind: "toggle", key: "context_compression_enabled", label: "启用上下文压缩", hint: "context_compression_enabled" },
];

const POOL_FIELDS: ConfigField<AgentPoolConfig>[] = [
  { kind: "number", key: "max_size", label: "最大容量", hint: "agent_pool.max_size", unit: "个", min: 1 },
  { kind: "number", key: "ttl_seconds", label: "TTL 秒数", hint: "agent_pool.ttl_seconds", unit: "秒", min: 0 },
  { kind: "number", key: "sweep_interval_seconds", label: "清理间隔秒数", hint: "agent_pool.sweep_interval_seconds", unit: "秒", min: 1 },
];

function toFormValue(config: InstanceConfig): ConfigFormValue {
  const agents = Object.entries(config.agents ?? {}).map(([code, agent]) => ({
    ...agent,
    code: agent.code || code,
    use_responses: agent.use_responses ?? false,
  }));
  return {
    agents,
    agent_pool: { ...DEFAULT_AGENT_POOL, ...(config.agent_pool ?? {}) },
    agent_runtime: { ...DEFAULT_AGENT_RUNTIME, ...(config.agent_runtime ?? {}) },
    integrations: { ...DEFAULT_INTEGRATIONS, ...(config.integrations ?? {}) },
  };
}

function cloneFormValue(values: ConfigFormValue): ConfigFormValue {
  return {
    agents: values.agents.map((agent) => ({ ...agent })),
    agent_pool: { ...values.agent_pool },
    agent_runtime: { ...values.agent_runtime },
    integrations: { ...values.integrations },
  };
}

function toPayload(values: ConfigFormValue): UpdateInstanceConfigRequest {
  const agents: NonNullable<UpdateInstanceConfigRequest["agents"]> = {};
  values.agents.forEach((agent) => {
    const code = agent.code.trim();
    if (!code) return;
    agents[code] = {
      name: agent.name.trim(),
      description: agent.description.trim(),
      base_url: agent.base_url.trim(),
      api_key: agent.api_key.trim(),
      model: agent.model.trim(),
      use_responses: agent.use_responses,
      context_window: agent.context_window,
    };
  });
  return {
    agents,
    agent_pool: values.agent_pool,
    agent_runtime: values.agent_runtime,
    integrations: {
      web_search_provider: values.integrations.web_search_provider ?? "auto",
      exa_api_key: values.integrations.exa_api_key ?? "",
      perplexity_api_key: values.integrations.perplexity_api_key ?? "",
      deepseek_api_key: values.integrations.deepseek_api_key ?? "",
      searxng_base_url: values.integrations.searxng_base_url ?? "",
      searxng_auto_provision: values.integrations.searxng_auto_provision ?? true,
      searxng_general_engines: values.integrations.searxng_general_engines ?? false,
    },
  };
}

// 与 toPayload 同口径分片：用于判断某个 Tab 是否有未保存改动。
function payloadSlices(values: ConfigFormValue): Record<Exclude<ConfigTabKey, "import">, string> {
  const payload = toPayload(values);
  return {
    agents: JSON.stringify(payload.agents),
    runtime: JSON.stringify([payload.agent_pool, payload.agent_runtime]),
    integrations: JSON.stringify(payload.integrations),
  };
}

const TAB_LABEL: Record<ConfigTabKey, string> = {
  agents: "模型预设",
  runtime: "运行参数",
  integrations: "联网检索",
  import: "快捷导入",
};

export function SystemConfigPage() {
  // 顶部 Tab：模型预设 / 运行参数 / 联网检索 / 快捷导入（原独立「快捷导入」页已并入）。
  const [activeTab, setActiveTab] = useState<ConfigTabKey>("agents");
  const [importHandle, setImportHandle] = useState<QuickImportHandle | null>(null);
  const [values, setValues] = useState<ConfigFormValue | null>(null);
  const [savedValues, setSavedValues] = useState<ConfigFormValue | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // 折叠区一律默认展开：这几块是「看一眼就想改」的配置，让用户少点几下。
  const [expandedCodes, setExpandedCodes] = useState<Set<string>>(new Set());
  const [runtimeOpen, setRuntimeOpen] = useState(true);
  const [poolOpen, setPoolOpen] = useState(true);
  const [integrationsOpen, setIntegrationsOpen] = useState(true);
  // 屏幕阅读器播报位（保存结果 / 放弃修改），不再只依赖 toast。
  const [announcement, setAnnouncement] = useState("");
  // 联网检索可用性校验结果（只探测、不保存）
  const [searchCheck, setSearchCheck] = useState<CheckSearchProvidersResponse["data"] | null>(null);
  const [searchChecking, setSearchChecking] = useState(false);

  const runSearchCheck = useCallback(async () => {
    if (!values) return;
    setSearchChecking(true);
    try {
      const response = await checkSearchProviders({
        exa_api_key: values.integrations.exa_api_key ?? "",
        perplexity_api_key: values.integrations.perplexity_api_key ?? "",
        deepseek_api_key: values.integrations.deepseek_api_key ?? "",
        searxng_base_url: values.integrations.searxng_base_url ?? "",
        deepseek_base_url: (savedValues?.integrations as { deepseek_base_url?: string } | undefined)?.deepseek_base_url ?? "",
      });
      const data = response.data;
      if (data) {
        setSearchCheck(data);
        const failed = data.results.filter((item) => item.configured && !item.ok).length;
        if (failed === 0) {
          showApiSuccess({ code: 200, message: "检索配置校验通过" });
        } else {
          showApiError(new Error(`${failed} 个已配置的 provider 校验未通过`));
        }
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setSearchChecking(false);
    }
  }, [values, savedValues]);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getInstanceConfig();
      if (response.data) {
        const nextValues = toFormValue(response.data);
        setValues(nextValues);
        setSavedValues(cloneFormValue(nextValues));
        // 默认把所有模型预设行也展开（与分区一致：进来就能直接改）。
        setExpandedCodes(new Set(nextValues.agents.map((agent) => agent.code)));
      }
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const tabDirty = useMemo<Record<Exclude<ConfigTabKey, "import">, boolean>>(() => {
    if (!values || !savedValues) {
      return { agents: false, runtime: false, integrations: false };
    }
    const current = payloadSlices(values);
    const saved = payloadSlices(savedValues);
    return {
      agents: current.agents !== saved.agents,
      runtime: current.runtime !== saved.runtime,
      integrations: current.integrations !== saved.integrations,
    };
  }, [savedValues, values]);

  const dirty = tabDirty.agents || tabDirty.runtime || tabDirty.integrations;
  const dirtyTabs = (Object.keys(tabDirty) as Array<Exclude<ConfigTabKey, "import">>)
    .filter((key) => tabDirty[key])
    .map((key) => TAB_LABEL[key]);

  const status = useMemo(() => {
    const agents = values?.agents ?? [];
    const total = agents.length;
    const missing = agents.filter((agent) => !agent.api_key.trim()).length;
    const rootConfigured = Boolean(agents[0]?.api_key.trim());
    if (total === 0) {
      return { tone: "warn", title: "没有可用的模型预设", detail: "当前实例未配置任何模型预设" };
    }
    if (!rootConfigured) {
      return {
        tone: "danger",
        title: "主线不可用",
        detail: `${missing} / ${total} 个模型预设未配置密钥 · 发起会话会在模型调用处返回 401`,
      };
    }
    if (missing > 0) {
      return {
        tone: "warn",
        title: "部分预设缺密钥",
        detail: `${missing} / ${total} 个模型预设未配置密钥 · 相关预设无法调用模型`,
      };
    }
    return { tone: "ok", title: "全部预设就绪", detail: `${total} 个模型预设均已配置密钥` };
  }, [values]);

  const numbers = useMemo(() => {
    const runtime = values?.agent_runtime;
    return [
      { label: "预设", value: String(values?.agents.length ?? "-") },
      { label: "池", value: String(values?.agent_pool.max_size ?? "-") },
      { label: "主轮次", value: String(runtime?.main_max_turns ?? "-") },
      { label: "压缩", value: runtime ? runtime.context_compression_trigger_ratio.toFixed(2) : "-" },
    ];
  }, [values]);

  const updatePool = (patch: Partial<AgentPoolConfig>) => {
    setValues((current) => current && { ...current, agent_pool: { ...current.agent_pool, ...patch } });
  };

  const updateRuntime = (patch: Partial<AgentRuntimeConfig>) => {
    setValues((current) => current && { ...current, agent_runtime: { ...current.agent_runtime, ...patch } });
  };

  const updateAgent = (code: string, patch: Partial<AgentConfig>) => {
    setValues((current) => current && {
      ...current,
      agents: current.agents.map((agent) => (agent.code === code ? { ...agent, ...patch } : agent)),
    });
  };

  const updateIntegrations = (patch: Partial<IntegrationsConfig>) => {
    setValues((current) => current && {
      ...current,
      integrations: { ...current.integrations, ...patch },
    });
  };

  const handleCancel = useCallback(() => {
    if (savedValues) {
      setValues(cloneFormValue(savedValues));
      setAnnouncement("已放弃未保存的修改");
    }
  }, [savedValues]);

  const handleSave = useCallback(async () => {
    if (!values || saving) return;

    setSaving(true);
    try {
      const response = await updateInstanceConfig(toPayload(values));
      showApiSuccess(response);
      if (response.data?.config) {
        const nextValues = toFormValue(response.data.config);
        setValues(nextValues);
        setSavedValues(cloneFormValue(nextValues));
      }
      setAnnouncement("实例配置已保存");
    } catch (error) {
      showApiError(error);
      setAnnouncement("保存失败，请查看错误提示");
    } finally {
      setSaving(false);
    }
  }, [saving, values]);

  const headerActions = useMemo(() => (
    <>
      <Button icon={<X size={16} />} type="tertiary" disabled={!dirty || saving || loading} onClick={handleCancel}>
        取消
      </Button>
      <Button icon={<Save size={16} />} theme="solid" type="primary" loading={saving} disabled={!dirty} onClick={handleSave}>
        保存
      </Button>
    </>
  ), [dirty, handleCancel, handleSave, loading, saving]);

  // 头栏动作随 Tab 切换：配置类 Tab 显示「放弃修改 / 保存」，快捷导入 Tab 显示「清空草稿」。
  const tabHeaderActions = useMemo(
    () => (activeTab === "import" ? (
      <Button
        icon={<Eraser size={16} />}
        type="tertiary"
        disabled={!importHandle}
        onClick={() => importHandle?.clearDraft()}
      >
        清空草稿
      </Button>
    ) : headerActions),
    [activeTab, headerActions, importHandle],
  );

  useAdminResourceHeader({
    refreshLabel: activeTab === "import" ? "刷新智能体" : "刷新配置",
    loading: activeTab === "import" ? Boolean(importHandle?.busy) : loading,
    onRefresh: activeTab === "import" ? () => importHandle?.refresh() : loadConfig,
    extraActions: tabHeaderActions,
    appendExtraActions: true,
  });

  return (
    <section className="system-config-page">
      <div className="cfg-sbar">
        <span className="st">
          <i className={cx("dot", status.tone !== "danger" && status.tone)} aria-hidden="true" />
          {status.title}
        </span>
        <span className="meta">{status.detail}</span>
        <span className="nums">
          {numbers.map((item) => (
            <i key={item.label}>{item.label} <b>{item.value}</b></i>
          ))}
          {activeTab !== "import" && tabDirty[activeTab] ? <i className="flag">未保存</i> : null}
        </span>
      </div>

      <p className="sr-only" role="status" aria-atomic="true">{announcement}</p>

      {dirty ? (
        <div className="cfg-dirty">
          <strong>有未保存的修改</strong>
          <span>{dirtyTabs.join(" · ")}</span>
          <span>改动仅保留在当前页面，点击右上角「保存」后写入实例配置。</span>
        </div>
      ) : null}

      <Spin spinning={loading} wrapperClassName="system-config-spin">
        {values ? (
          <Tabs
            type="line"
            className="system-config-tabs"
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as ConfigTabKey)}
          >
            <TabPane tab={<TabLabel text={TAB_LABEL.agents} dirty={tabDirty.agents} />} itemKey="agents">
              <div className="system-config-layout">
            <div className="config-panel">
              <div className="config-panel-header">
                <div>
                  <h2 id="cfg-agents-title">模型预设</h2>
                </div>
                <span className={cx("chip", status.tone)}>
                  {status.tone !== "ok" ? <i className="dot" aria-hidden="true" /> : null}
                  {values.agents.filter((agent) => agent.api_key.trim()).length} / {values.agents.length} 已配置密钥
                </span>
              </div>
              <table className="cfg-ptable" aria-labelledby="cfg-agents-title">
                <thead>
                  <tr>
                    <th scope="col" className="expander"><span className="sr-only">展开编辑</span></th>
                    <th scope="col">代码</th>
                    <th scope="col">名称</th>
                    <th scope="col">模型</th>
                    <th scope="col">密钥</th>
                  </tr>
                </thead>
                <tbody>
                  {values.agents.map((agent) => (
                    <AgentPresetRow
                      key={agent.code}
                      agent={agent}
                      open={expandedCodes.has(agent.code)}
                      onToggle={() => setExpandedCodes((current) => {
                        const next = new Set(current);
                        if (next.has(agent.code)) {
                          next.delete(agent.code);
                        } else {
                          next.add(agent.code);
                        }
                        return next;
                      })}
                      onChange={(patch) => updateAgent(agent.code, patch)}
                    />
                  ))}
                </tbody>
              </table>
              <div className="cfg-legend">
                <span>点任意一行就地展开编辑 · 先填主预设 {values.agents[0]?.code ?? "cso"} 即可让主线可跑</span>
              </div>
            </div>
              </div>
            </TabPane>

            <TabPane tab={<TabLabel text={TAB_LABEL.runtime} dirty={tabDirty.runtime} />} itemKey="runtime">
              <div className="system-config-layout">
            <div className="config-panel">
              <FoldHeader
                id="cfg-runtime"
                title="运行参数"
                summary={`${RUNTIME_FIELDS.length} 项 · 压缩${values.agent_runtime.context_compression_enabled ? "启用" : "禁用"} · 触发 ${values.agent_runtime.context_compression_trigger_ratio.toFixed(2)}`}
                open={runtimeOpen}
                onToggle={() => setRuntimeOpen((current) => !current)}
              />
              {runtimeOpen ? (
                <div className="cfg-plist" id="cfg-runtime-body">
                  <ParamGrid fields={RUNTIME_FIELDS} values={values.agent_runtime} onChange={updateRuntime} />
                </div>
              ) : null}
            </div>

            <div className="config-panel">
              <FoldHeader
                id="cfg-pool"
                title="Agent 池"
                summary={`${POOL_FIELDS.length} 项 · 上限 ${values.agent_pool.max_size} · TTL ${values.agent_pool.ttl_seconds}s`}
                open={poolOpen}
                onToggle={() => setPoolOpen((current) => !current)}
              />
              {poolOpen ? (
                <div className="cfg-plist" id="cfg-pool-body">
                  <ParamGrid fields={POOL_FIELDS} values={values.agent_pool} onChange={updatePool} />
                </div>
              ) : null}
            </div>
              </div>
            </TabPane>

            <TabPane tab={<TabLabel text={TAB_LABEL.integrations} dirty={tabDirty.integrations} />} itemKey="integrations">
              <div className="system-config-layout">
            <div className="config-panel">
              <FoldHeader
                id="cfg-integrations"
                title="联网检索"
                summary={integrationsSummary(values.integrations)}
                open={integrationsOpen}
                onToggle={() => setIntegrationsOpen((current) => !current)}
              />
              {integrationsOpen ? (
                <div className="cfg-plist" id="cfg-integrations-body">
                  <div className="cfg-pg">
                    <Field id="cfg-provider" label="Provider">
                      <select
                        id="cfg-provider"
                        value={values.integrations.web_search_provider ?? "auto"}
                        onChange={(event) => updateIntegrations({
                          web_search_provider: event.target.value as NonNullable<IntegrationsConfig["web_search_provider"]>,
                        })}
                      >
                        <option value="auto">auto（检索：Exa → Perplexity → 自建 SearXNG；页面抓取优先用 DeepSeek）</option>
                        <option value="exa">exa</option>
                        <option value="perplexity">perplexity</option>
                        <option value="searxng">searxng（自建，无需 key）</option>
                        <option value="deepseek">deepseek（检索走 DeepSeek，按次计费、5 QPS）</option>
                      </select>
                    </Field>
                    <Field id="cfg-exa" label="Exa API 密钥" className="full">
                      <SecretInput
                        id="cfg-exa"
                        value={values.integrations.exa_api_key ?? ""}
                        onChange={(next) => updateIntegrations({ exa_api_key: next })}
                      />
                    </Field>
                    <Field id="cfg-perplexity" label="Perplexity API 密钥" className="full">
                      <SecretInput
                        id="cfg-perplexity"
                        value={values.integrations.perplexity_api_key ?? ""}
                        onChange={(next) => updateIntegrations({ perplexity_api_key: next })}
                      />
                    </Field>
                    <Field id="cfg-deepseek" label="DeepSeek API 密钥（检索与页面抓取共用）" className="full">
                      <SecretInput
                        id="cfg-deepseek"
                        value={values.integrations.deepseek_api_key ?? ""}
                        onChange={(next) => updateIntegrations({ deepseek_api_key: next })}
                      />
                      <span className="project-form-hint">
                        计费：按「成功请求次数」计价 —— Search 与 Fetch 各 5 元 / 1000 次；无结果、失败、超时都不计费，返回条数不影响单价。
                      </span>
                      <span className="qi-hint">
                        限速：账号级 Search 与 Fetch 各自 5 QPS（与用哪把密钥无关），超限返回 429；provider 选 deepseek 时「检索」也走这把密钥，选 auto 时检索不产生 DeepSeek 费用。
                      </span>
                    </Field>
                    <Field id="cfg-searxng" label="SearXNG 地址" className="full">
                      <input
                        id="cfg-searxng"
                        type="text"
                        value={values.integrations.searxng_base_url ?? ""}
                        placeholder="http://127.0.0.1:8888"
                        onChange={(event) => updateIntegrations({ searxng_base_url: event.target.value })}
                      />
                    </Field>
                    <ToggleField
                      id="cfg-auto-provision"
                      label="自动拉起容器"
                      hint="searxng_auto_provision"
                      checked={values.integrations.searxng_auto_provision ?? true}
                      onToggle={() => updateIntegrations({
                        searxng_auto_provision: !(values.integrations.searxng_auto_provision ?? true),
                      })}
                    />
                    <ToggleField
                      id="cfg-general-engines"
                      label="通用引擎（Google / Bing / DuckDuckGo / Brave）"
                      hint="searxng_general_engines"
                      checked={values.integrations.searxng_general_engines ?? false}
                      onToggle={() => updateIntegrations({
                        searxng_general_engines: !(values.integrations.searxng_general_engines ?? false),
                      })}
                    />
                  </div>
                  <div className="cfg-check">
                    <div className="cfg-check-head">
                      <div>
                        <strong>可用性校验</strong>
                        <span className="project-form-hint">
                          逐个探测已填的 provider（不保存配置）。Exa / Perplexity / 无 /models 的 DeepSeek 网关会发起一次真实请求，可能产生极小费用。
                        </span>
                      </div>
                      <Button
                        type="primary"
                        theme="borderless"
                        size="small"
                        loading={searchChecking}
                        onClick={() => void runSearchCheck()}
                      >
                        测试连通性
                      </Button>
                    </div>
                    {searchCheck ? (
                      <>
                        <table className="cfg-check-table">
                          <thead>
                            <tr>
                              <th>Provider</th>
                              <th>结果</th>
                              <th>说明</th>
                              <th>耗时</th>
                            </tr>
                          </thead>
                          <tbody>
                            {searchCheck.results.map((item) => (
                              <tr key={item.provider}>
                                <td>{item.provider}</td>
                                <td>
                                  <span className={cx("cfg-check-badge", item.ok ? "ok" : item.configured ? "bad" : "idle")}>
                                    {item.ok ? "可用" : item.configured ? "不可用" : "未配置"}
                                  </span>
                                </td>
                                <td>{item.detail}</td>
                                <td>{item.elapsed_ms} ms</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        <div className="project-form-hint">
                          auto 模式当前会选中：
                          <strong>{searchCheck.recommended ?? "无可用 provider（检索将降级为内置安全数据库）"}</strong>
                        </div>
                      </>
                    ) : null}
                  </div>
                  <div className="cfg-legend">
                    <span>密钥经环境变量注入沙箱 · provider=searxng 时用自建实例，无需 key；provider=deepseek 时检索走 DeepSeek（按次计费、账号级 5 QPS），页面抓取也用它，密钥留空则自动跟随「模型配置」里已填的 DeepSeek key；「自动拉起容器」= 本机 SearXNG 不可达时平台自动 docker start / run（关掉则只注入配置、不碰容器）；「通用引擎」= 打开后平台改写 SearXNG 配置把 Google / Bing / DuckDuckGo / Brave 设为启用并重启容器（默认关：这几个引擎在部分网络被墙或要验证码）</span>
                  </div>
                </div>
              ) : null}
            </div>
              </div>
            </TabPane>

            <TabPane tab={<TabLabel text={TAB_LABEL.import} dirty={false} />} itemKey="import">
              <QuickImportPanel onHandle={setImportHandle} />
            </TabPane>
          </Tabs>
        ) : null}
      </Spin>
    </section>
  );
}

function AgentPresetRow({ agent, open, onToggle, onChange }: {
  agent: AgentFormValue;
  open: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<AgentConfig>) => void;
}) {
  const configured = Boolean(agent.api_key.trim());
  const detailId = `cfg-agent-${agent.code}`;
  return (
    <>
      <tr className={cx("cfg-prow", open && "open")} onClick={onToggle}>
        <td className="expander">
          <button
            type="button"
            className={cx("exp", open && "open")}
            aria-expanded={open}
            aria-controls={detailId}
            aria-label={`${open ? "收起" : "展开"} ${agent.name || agent.code} 的编辑区`}
            onClick={(event) => {
              event.stopPropagation();
              onToggle();
            }}
          >
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </td>
        <td className="code"><span className="mono">{agent.code}</span></td>
        <td><strong>{agent.name || agent.code}</strong></td>
        <td className="mono model">{agent.model || "—"}</td>
        <td className="state">
          <span className={cx("chip", configured ? "ok" : "danger")}>
            {configured ? null : <i className="dot" aria-hidden="true" />}
            {configured ? "已配置" : "密钥缺失"}
          </span>
        </td>
      </tr>
      {open ? (
        <tr className="cfg-pedit">
          <td colSpan={5}>
            <div className="cfg-pg" id={detailId}>
              <Field id={`${detailId}-name`} label="名称">
                <input
                  id={`${detailId}-name`}
                  type="text"
                  value={agent.name}
                  maxLength={128}
                  onChange={(event) => onChange({ name: event.target.value })}
                />
              </Field>
              <Field id={`${detailId}-model`} label="模型">
                <input
                  id={`${detailId}-model`}
                  type="text"
                  value={agent.model}
                  onChange={(event) => onChange({ model: event.target.value })}
                />
              </Field>
              <Field id={`${detailId}-context`} label="上下文窗口">
                <input
                  id={`${detailId}-context`}
                  type="number"
                  min={0}
                  value={agent.context_window}
                  onChange={(event) => onChange({ context_window: Number(event.target.value) || 0 })}
                />
              </Field>
              <Field id={`${detailId}-key`} label="API 密钥">
                <SecretInput
                  id={`${detailId}-key`}
                  value={agent.api_key}
                  onChange={(next) => onChange({ api_key: next })}
                />
              </Field>
              <Field id={`${detailId}-base`} label="基础 URL">
                <input
                  id={`${detailId}-base`}
                  type="text"
                  value={agent.base_url}
                  onChange={(event) => onChange({ base_url: event.target.value })}
                />
              </Field>
              <ToggleField
                id={`${detailId}-responses`}
                label="使用 Responses API"
                hint="use_responses"
                checked={agent.use_responses}
                onToggle={() => onChange({ use_responses: !agent.use_responses })}
              />
              <Field id={`${detailId}-desc`} label="描述" className="full">
                <textarea
                  id={`${detailId}-desc`}
                  rows={2}
                  value={agent.description}
                  onChange={(event) => onChange({ description: event.target.value })}
                />
              </Field>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  );
}

/* ───────────────── 结构件 ───────────────── */

// Tab 标签：带未保存改动标记（视觉圆点 + 屏幕阅读器文案）。
function TabLabel({ text, dirty }: { text: string; dirty: boolean }) {
  return (
    <span className="cfg-tab">
      {text}
      {dirty ? (
        <>
          <i className="cfg-tab-dot" aria-hidden="true" />
          <span className="sr-only">（有未保存的修改）</span>
        </>
      ) : null}
    </span>
  );
}

// 表单字段：真实 label（for/id 关联）+ 可选错误槽位。
function Field({ id, label, className, children }: {
  id: string;
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("cfg-field", className)}>
      <label className="cfg-field-label" htmlFor={id}>{label}</label>
      {children}
    </div>
  );
}

// 密钥输入：明/密文切换 + 「已配置 / 未配置」标记，不再只靠 placeholder。
function SecretInput({ id, value, onChange }: {
  id: string;
  value: string;
  onChange: (next: string) => void;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <span className="cfg-input-wrap">
      <input
        id={id}
        type={revealed ? "text" : "password"}
        value={value}
        placeholder="未配置"
        autoComplete="off"
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        className={cx("cfg-reveal", revealed && "on")}
        aria-pressed={revealed}
        aria-label={`${revealed ? "隐藏" : "显示"}密钥明文`}
        onClick={() => setRevealed((current) => !current)}
      >
        {revealed ? <EyeOff size={13} aria-hidden="true" /> : <Eye size={13} aria-hidden="true" />}
      </button>
    </span>
  );
}

// 开关字段：button 不是 labelable 元素，故用 span + aria-labelledby 关联。
function ToggleField({ id, label, hint, checked, onToggle }: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onToggle: () => void;
}) {
  const labelId = `${id}-label`;
  const hintId = `${id}-hint`;
  return (
    <div className="cfg-field tog">
      <span className="cfg-field-label" id={labelId}>
        {label}
        <em id={hintId}>{hint}</em>
      </span>
      <button
        type="button"
        className="sw"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        aria-describedby={hintId}
        onClick={onToggle}
      />
    </div>
  );
}

function FoldHeader({ id, title, summary, open, onToggle }: {
  id: string;
  title: string;
  summary: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={cx("cfg-fold", open && "open")}
      aria-expanded={open}
      aria-controls={`${id}-body`}
      onClick={onToggle}
    >
      <span className="tt">{title}</span>
      <span className="sm">{summary}</span>
      <ChevronRight className="cv" size={14} aria-hidden="true" />
    </button>
  );
}

function ParamGrid<T extends object>({ fields, values, onChange }: {
  fields: ConfigField<T>[];
  values: T;
  onChange: (patch: Partial<T>) => void;
}) {
  const rows: ConfigField<T>[][] = [];
  for (let index = 0; index < fields.length; index += 2) {
    rows.push(fields.slice(index, index + 2));
  }

  return (
    <>
      {rows.map((pair) => (
        <div className="cfg-prow2" key={String(pair[0].key)}>
          {pair.map((field) => (
            <ParamCell key={String(field.key)} field={field} values={values} onChange={onChange} />
          ))}
          {pair.length === 1 ? <><span /><span /></> : null}
        </div>
      ))}
    </>
  );
}

function ParamCell<T extends object>({ field, values, onChange }: {
  field: ConfigField<T>;
  values: T;
  onChange: (patch: Partial<T>) => void;
}) {
  const fieldId = `cfg-param-${String(field.key)}`;
  const hintId = `${fieldId}-hint`;

  if (field.kind === "toggle") {
    return (
      <>
        <span className="lab tog" id={fieldId}>
          {field.label}
          <em id={hintId}>{field.hint}</em>
        </span>
        <button
          type="button"
          className="sw"
          role="switch"
          aria-checked={values[field.key] as boolean}
          aria-labelledby={fieldId}
          aria-describedby={hintId}
          onClick={() => onChange({ [field.key]: !values[field.key] } as Partial<T>)}
        />
      </>
    );
  }

  const value = values[field.key] as number;
  const overflowed = (field.min !== undefined && value < field.min)
    || (field.max !== undefined && value > field.max);
  const range = field.min !== undefined && field.max !== undefined
    ? `取值 ${field.min} – ${field.max}`
    : field.min !== undefined
      ? `不小于 ${field.min}`
      : "";
  return (
    <>
      <label className="lab" htmlFor={fieldId}>
        {field.label}
        <em id={hintId}>{field.hint}</em>
      </label>
      <span className={cx("cfg-num", overflowed && "invalid")}>
        <input
          id={fieldId}
          className="bare"
          type="number"
          value={value}
          min={field.min}
          max={field.max}
          step={field.step}
          aria-describedby={hintId}
          aria-invalid={overflowed || undefined}
          title={range || undefined}
          onChange={(event) => onChange({ [field.key]: Number(event.target.value) } as Partial<T>)}
        />
        {field.unit ? <i className="unit">{field.unit}</i> : null}
      </span>
    </>
  );
}
