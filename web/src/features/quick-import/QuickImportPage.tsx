import { Button, Spin } from "@douyinfe/semi-ui";
import { Download, Eye } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../shared/api/client";
import { fetchUpstreamModels, getInstanceConfig, updateInstanceConfig } from "../../shared/api/systemConfig";
import { showApiError, showApiSuccess } from "../../shared/api/feedback";
import { cx } from "../../shared/lib/className";
import type { InstanceConfig, UpdateInstanceConfigRequest } from "../../shared/api/types";

/** 交给「系统配置」父页面渲染头栏按钮所需的动作句柄。 */
export type QuickImportHandle = {
  refresh: () => void;
  clearDraft: () => void;
  busy: boolean;
};

type QuickImportPanelProps = {
  onHandle?: (handle: QuickImportHandle | null) => void;
};

const DRAFT_STORAGE_KEY = "ravenholt.quick-import.draft";
const CUSTOM_VENDOR_ID = "custom";
const DEFAULT_CONTEXT_WINDOW = 128000;

type VendorPreset = { id: string; label: string; baseUrl: string };

const VENDOR_PRESETS: VendorPreset[] = [
  { id: "deepseek", label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1" },
  { id: "qwen", label: "通义千问", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { id: "zhipu", label: "智谱 GLM", baseUrl: "https://open.bigmodel.cn/api/paas/v4" },
  { id: "moonshot", label: "Moonshot", baseUrl: "https://api.moonshot.cn/v1" },
  { id: "siliconflow", label: "硅基流动", baseUrl: "https://api.siliconflow.cn/v1" },
  { id: "minimax", label: "MiniMax", baseUrl: "https://api.minimax.chat/v1" },
  { id: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1" },
];

type DraftModel = { id: string; checked: boolean; contextWindow: number };

type Draft = {
  vendorId: string;
  customName: string;
  customBaseUrl: string;
  apiKey: string;
  models: DraftModel[];
};

const EMPTY_DRAFT: Draft = {
  vendorId: VENDOR_PRESETS[0].id,
  customName: "",
  customBaseUrl: "",
  apiKey: "",
  models: [],
};

type PlanChange = { label: string; from: string; to: string };
type PlanItem = { code: string; name: string; changes: PlanChange[] };
type PlanFailure = { code: string; name: string; reason: string };

type Plan = {
  mode: "key-only" | "models";
  items: PlanItem[];
  ignored: string[];
  failures: PlanFailure[];
  baseUrl: string;
  apiKeyHint: string;
};

type ImportResult = {
  successCount: number;
  failures: PlanFailure[];
  mode: Plan["mode"];
};

function loadDraft(): Draft {
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) return { ...EMPTY_DRAFT };
    const parsed = JSON.parse(raw) as Partial<Draft>;
    return {
      vendorId: typeof parsed.vendorId === "string" && parsed.vendorId ? parsed.vendorId : EMPTY_DRAFT.vendorId,
      customName: typeof parsed.customName === "string" ? parsed.customName : "",
      customBaseUrl: typeof parsed.customBaseUrl === "string" ? parsed.customBaseUrl : "",
      apiKey: typeof parsed.apiKey === "string" ? parsed.apiKey : "",
      models: Array.isArray(parsed.models)
        ? parsed.models
            .filter((item): item is DraftModel => Boolean(item) && typeof item.id === "string")
            .map((item) => ({
              id: item.id,
              checked: Boolean(item.checked),
              contextWindow: Number(item.contextWindow) || DEFAULT_CONTEXT_WINDOW,
            }))
        : [],
    };
  } catch {
    return { ...EMPTY_DRAFT };
  }
}

function isDraftEmpty(draft: Draft): boolean {
  return (
    draft.apiKey.trim() === ""
    && draft.customName.trim() === ""
    && draft.customBaseUrl.trim() === ""
    && draft.models.length === 0
  );
}

function resolveBaseUrl(draft: Draft): string {
  if (draft.vendorId === CUSTOM_VENDOR_ID) return draft.customBaseUrl.trim();
  return VENDOR_PRESETS.find((preset) => preset.id === draft.vendorId)?.baseUrl ?? "";
}

function resolveVendorLabel(draft: Draft): string {
  if (draft.vendorId === CUSTOM_VENDOR_ID) return draft.customName.trim() || "自定义厂商";
  return VENDOR_PRESETS.find((preset) => preset.id === draft.vendorId)?.label ?? "未选择";
}

function maskKey(key: string): string {
  const trimmed = key.trim();
  if (trimmed.length <= 8) return "••••••";
  return `••••••${trimmed.slice(-4)}`;
}

function buildPlan(config: InstanceConfig, draft: Draft): Plan {
  const baseUrl = resolveBaseUrl(draft);
  const apiKey = draft.apiKey.trim();
  const entries = Object.entries(config.agents ?? {});
  const selected = draft.models.filter((model) => model.checked);
  const mode: Plan["mode"] = selected.length > 0 ? "models" : "key-only";
  const apiKeyHint = apiKey ? maskKey(apiKey) : "未填写";

  const failures: PlanFailure[] = [];
  if (entries.length === 0) {
    failures.push({ code: "—", name: "没有可配置的智能体", reason: "当前实例没有任何智能体" });
  }
  if (!baseUrl) {
    failures.push({ code: "—", name: "缺少基础 URL", reason: "请选择厂商预设或填写自定义基础 URL" });
  }
  if (!apiKey) {
    failures.push({ code: "—", name: "缺少 API 密钥", reason: "请填写 API 密钥" });
  }
  if (failures.length > 0) {
    return { mode, items: [], ignored: [], failures, baseUrl, apiKeyHint };
  }

  const items: PlanItem[] = [];
  const ignored: string[] = [];

  if (mode === "key-only") {
    entries.forEach(([code, agent]) => {
      items.push({
        code,
        name: agent.name || code,
        changes: [
          { label: "API 密钥", from: agent.api_key ? maskKey(agent.api_key) : "未配置", to: apiKeyHint },
          { label: "基础 URL", from: agent.base_url || "—", to: baseUrl },
        ],
      });
    });
  } else {
    entries.forEach(([code, agent], index) => {
      const model = selected[index];
      if (!model) return;
      items.push({
        code,
        name: agent.name || code,
        changes: [
          { label: "模型", from: agent.model || "—", to: model.id },
          { label: "上下文长度", from: String(agent.context_window), to: String(model.contextWindow) },
          { label: "API 密钥", from: agent.api_key ? maskKey(agent.api_key) : "未配置", to: apiKeyHint },
          { label: "基础 URL", from: agent.base_url || "—", to: baseUrl },
        ],
      });
    });
    selected.slice(entries.length).forEach((model) => ignored.push(model.id));
  }

  return { mode, items, ignored, failures, baseUrl, apiKeyHint };
}

function buildPayload(config: InstanceConfig, draft: Draft, plan: Plan): UpdateInstanceConfigRequest {
  const apiKey = draft.apiKey.trim();
  const selected = draft.models.filter((model) => model.checked);
  const overrides = new Map<string, { model: string; contextWindow: number }>();
  if (plan.mode === "models") {
    Object.keys(config.agents ?? {}).forEach((code, index) => {
      const model = selected[index];
      if (model) overrides.set(code, { model: model.id, contextWindow: model.contextWindow });
    });
  }

  const agents: NonNullable<UpdateInstanceConfigRequest["agents"]> = {};
  Object.entries(config.agents ?? {}).forEach(([code, agent]) => {
    const override = overrides.get(code);
    const applyKey = plan.mode === "key-only" || override !== undefined;
    agents[code] = {
      name: agent.name,
      description: agent.description,
      base_url: applyKey ? plan.baseUrl : agent.base_url,
      api_key: applyKey ? apiKey : agent.api_key,
      model: override?.model ?? agent.model,
      use_responses: agent.use_responses ?? false,
      context_window: override?.contextWindow ?? agent.context_window,
    };
  });

  // 实例配置接口始终返回 agent_pool / agent_runtime / integrations，仅 TS 契约标记为可选
  return {
    agents,
    agent_pool: config.agent_pool!,
    agent_runtime: config.agent_runtime!,
    integrations: config.integrations!,
  };
}

export function QuickImportPanel({ onHandle }: QuickImportPanelProps) {
  const [draft, setDraft] = useState<Draft>(() => loadDraft());
  const [config, setConfig] = useState<InstanceConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    if (isDraftEmpty(draft)) {
      window.localStorage.removeItem(DRAFT_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  }, [draft]);

  const loadConfig = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getInstanceConfig();
      if (response.data) setConfig(response.data);
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const baseUrl = resolveBaseUrl(draft);
  const vendorLabel = resolveVendorLabel(draft);
  const selectedModels = useMemo(() => draft.models.filter((model) => model.checked), [draft.models]);
  const agentCount = useMemo(() => Object.keys(config?.agents ?? {}).length, [config]);

  const patchDraft = (patch: Partial<Draft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setPlan(null);
    setResult(null);
  };

  const handleFetchModels = useCallback(async () => {
    if (!baseUrl || !draft.apiKey.trim()) return;
    setFetching(true);
    setFetchError(null);
    try {
      const response = await fetchUpstreamModels({ base_url: baseUrl, api_key: draft.apiKey.trim() });
      const models = response.data?.models ?? [];
      const previous = new Map(draft.models.map((model) => [model.id, model]));
      setDraft((current) => ({
        ...current,
        models: models.map((id: string) => previous.get(id) ?? { id, checked: false, contextWindow: DEFAULT_CONTEXT_WINDOW }),
      }));
      setPlan(null);
      setResult(null);
    } catch (error) {
      setFetchError(errorMessage(error));
      showApiError(error);
    } finally {
      setFetching(false);
    }
  }, [baseUrl, draft.apiKey, draft.models]);

  const handlePreview = useCallback(() => {
    if (!config) return;
    setResult(null);
    setPlan(buildPlan(config, draft));
  }, [config, draft]);

  const handleConfirm = useCallback(async () => {
    if (!config || !plan || plan.failures.length > 0 || importing) return;
    setImporting(true);
    try {
      const response = await updateInstanceConfig(buildPayload(config, draft, plan));
      showApiSuccess(response);
      if (response.data?.config) setConfig(response.data.config);
      setResult({ successCount: plan.items.length, failures: plan.failures, mode: plan.mode });
      setPlan(null);
      window.localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch (error) {
      showApiError(error);
      setResult({ successCount: 0, failures: [{ code: "—", name: "批量导入失败", reason: errorMessage(error) }], mode: plan.mode });
    } finally {
      setImporting(false);
    }
  }, [config, draft, importing, plan]);

  const handleClearDraft = useCallback(() => {
    setDraft({ ...EMPTY_DRAFT });
    setPlan(null);
    setResult(null);
    setFetchError(null);
    window.localStorage.removeItem(DRAFT_STORAGE_KEY);
  }, []);

  // 合并进「系统配置」后，头栏按钮由父页面按当前 Tab 渲染：这里只把动作交给父组件。
  useEffect(() => {
    if (!onHandle) return;
    onHandle({ refresh: loadConfig, clearDraft: handleClearDraft, busy: loading || fetching || importing });
    return () => onHandle(null);
  }, [onHandle, loadConfig, handleClearDraft, loading, fetching, importing]);

  return (
    <div className="qi-panel">
      <p className="qi-intro">
        批量把当前实例的全部智能体统一配置为同一套 API 参数。仅填写 API 密钥即按「仅配置密钥」模式执行；勾选模型后按勾选顺序依次分配给前 N 个智能体。
      </p>

      <Spin spinning={loading} wrapperClassName="system-config-spin">
        <div className="system-config-layout">
          <div className="config-panel">
            <div className="config-panel-header">
              <div><h2>厂商与密钥</h2></div>
              <span className="chip">{vendorLabel}</span>
            </div>
            <div className="qi-body">
              <div className="qi-vendors">
                {VENDOR_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    className={cx("qi-vendor", draft.vendorId === preset.id && "on")}
                    onClick={() => patchDraft({ vendorId: preset.id })}
                  >
                    {preset.label}
                  </button>
                ))}
                <button
                  type="button"
                  className={cx("qi-vendor", draft.vendorId === CUSTOM_VENDOR_ID && "on")}
                  onClick={() => patchDraft({ vendorId: CUSTOM_VENDOR_ID })}
                >
                  自定义厂商
                </button>
              </div>

              {draft.vendorId === CUSTOM_VENDOR_ID ? (
                <div className="qi-custom">
                  <label className="qi-field">
                    <span>厂商名称</span>
                    <input
                      type="text"
                      value={draft.customName}
                      placeholder="例如：内网网关"
                      onChange={(event) => patchDraft({ customName: event.target.value })}
                    />
                  </label>
                  <label className="qi-field">
                    <span>基础 URL</span>
                    <input
                      type="text"
                      value={draft.customBaseUrl}
                      placeholder="https://example.com/v1"
                      onChange={(event) => patchDraft({ customBaseUrl: event.target.value })}
                    />
                  </label>
                </div>
              ) : (
                <div className="qi-resolved">
                  <span className="mono">{baseUrl}</span>
                </div>
              )}

              <label className="qi-field">
                <span>API 密钥</span>
                <input
                  type="password"
                  value={draft.apiKey}
                  placeholder="仅填写密钥即按「仅配置密钥」模式批量写入全部智能体"
                  onChange={(event) => patchDraft({ apiKey: event.target.value })}
                />
              </label>

              <div className="qi-fetch">
                <Button
                  icon={<Download size={16} />}
                  type="tertiary"
                  loading={fetching}
                  disabled={!baseUrl || !draft.apiKey.trim()}
                  onClick={handleFetchModels}
                >
                  获取模型列表
                </Button>
                <span className="qi-hint">将请求 {baseUrl || "—"}/models 拉取该厂商可用模型</span>
              </div>

              {fetchError ? <div className="qi-error">{fetchError}</div> : null}
            </div>
          </div>

          {draft.models.length > 0 ? (
            <div className="config-panel">
              <div className="config-panel-header">
                <div><h2>模型列表</h2></div>
                <span className="chip">已选 {selectedModels.length} / {draft.models.length}</span>
              </div>
              <div className="qi-models">
                {draft.models.map((model) => (
                  <div className="qi-model" key={model.id}>
                    <input
                      id={`qi-model-${model.id}`}
                      type="checkbox"
                      checked={model.checked}
                      onChange={(event) => patchDraft({
                        models: draft.models.map((item) => (
                          item.id === model.id ? { ...item, checked: event.target.checked } : item
                        )),
                      })}
                    />
                    <label className="id mono" htmlFor={`qi-model-${model.id}`}>{model.id}</label>
                    <label className="ctx">
                      <em>上下文长度</em>
                      <input
                        className="bare"
                        type="number"
                        min={0}
                        value={model.contextWindow}
                        onChange={(event) => patchDraft({
                          models: draft.models.map((item) => (
                            item.id === model.id ? { ...item, contextWindow: Number(event.target.value) || 0 } : item
                          )),
                        })}
                      />
                    </label>
                  </div>
                ))}
              </div>
              <div className="cfg-legend">
                <span>勾选顺序即分配顺序：第 1 个勾选的模型写入第 1 个智能体，以此类推；超出智能体数量的模型会被忽略。</span>
              </div>
            </div>
          ) : null}

          <div className="config-panel">
            <div className="config-panel-header">
              <div><h2>导入预览与执行</h2></div>
              <span className="chip">{selectedModels.length > 0 ? "按模型分配" : "仅配置密钥"}</span>
            </div>
            <div className="qi-body">
              <p className="qi-mode">
                {selectedModels.length > 0
                  ? `将把前 ${Math.min(selectedModels.length, agentCount)} 个智能体依次配置为所选模型（同时写入 API 密钥与基础 URL），其余智能体保持不变。`
                  : `未勾选模型，将把全部 ${agentCount} 个智能体的 API 密钥与基础 URL 统一改写为该厂商配置，其余参数保持不变。`}
              </p>

              {plan ? (
                <>
                  <table className="cfg-ptable qi-plantable">
                    <thead>
                      <tr><th>智能体</th><th>参数变更</th></tr>
                    </thead>
                    <tbody>
                      {plan.items.map((item) => (
                        <tr key={item.code}>
                          <td className="code"><span className="mono">{item.code}</span> {item.name}</td>
                          <td>
                            {item.changes.map((change) => (
                              <span className="qi-change" key={change.label}>
                                <em>{change.label}</em>
                                <s>{change.from}</s>
                                <b>{change.to}</b>
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {plan.ignored.length > 0 ? (
                    <div className="qi-warn">以下模型无对应智能体，将忽略：<span className="mono">{plan.ignored.join("、")}</span></div>
                  ) : null}

                  {plan.failures.length > 0 ? (
                    <div className="qi-error">
                      {plan.failures.map((failure) => (
                        <div key={`${failure.code}-${failure.name}`}>{failure.name}：{failure.reason}</div>
                      ))}
                    </div>
                  ) : null}

                  <div className="qi-actions">
                    <Button type="tertiary" onClick={() => setPlan(null)}>取消</Button>
                    <Button
                      theme="solid"
                      type="primary"
                      loading={importing}
                      disabled={plan.failures.length > 0 || plan.items.length === 0}
                      onClick={handleConfirm}
                    >
                      确认导入（{plan.items.length} 个智能体）
                    </Button>
                  </div>
                </>
              ) : (
                <div className="qi-actions">
                  <Button icon={<Eye size={16} />} type="tertiary" disabled={!config} onClick={handlePreview}>
                    预览导入
                  </Button>
                </div>
              )}
            </div>
          </div>

          {result ? (
            <div className="config-panel">
              <div className="config-panel-header">
                <div><h2>导入结果</h2></div>
                <span className={cx("chip", result.failures.length > 0 ? "danger" : "ok")}>
                  {result.failures.length > 0 && result.successCount === 0 ? "全部失败" : result.failures.length > 0 ? "部分失败" : "全部成功"}
                </span>
              </div>
              <div className="qi-body">
                <p className="qi-result">
                  {result.mode === "models" ? "按模型分配" : "仅配置密钥"} · 成功导入 <b>{result.successCount}</b> 个智能体
                  {result.failures.length > 0 ? <>，失败 <b className="danger">{result.failures.length}</b> 项</> : null}
                </p>
                {result.failures.length > 0 ? (
                  <table className="cfg-ptable qi-plantable">
                    <thead>
                      <tr><th>失败项</th><th>原因</th></tr>
                    </thead>
                    <tbody>
                      {result.failures.map((failure) => (
                        <tr key={`${failure.code}-${failure.name}`}>
                          <td className="code"><span className="mono">{failure.code}</span> {failure.name}</td>
                          <td>{failure.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="qi-ok">本地草稿已清除。</div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </Spin>
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.response?.message || error.message || "请求失败";
  if (error instanceof Error) return error.message;
  return "请求失败";
}
