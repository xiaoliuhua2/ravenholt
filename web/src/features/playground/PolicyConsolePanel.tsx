import { Button, InputNumber, Modal, Switch, TextArea, Toast } from "@douyinfe/semi-ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../../shared/api/client";
import { getPolicyActions, updatePolicyActions } from "../../shared/api/policyActions";
import { getPolicyConfig, setKillSwitch, updatePolicyConfig } from "../../shared/api/policyConfig";
import type {
  PolicyApprovalGates,
  PolicyConfig,
  UpdatePolicyActionsRequest,
  UpdatePolicyConfigRequest,
} from "../../shared/api/types";
import { cx } from "../../shared/lib/className";

type SectionKey = "scope" | "denylist" | "dos" | "rate_limit";

/** 生成的契约里带默认值的字段都是可选的，这里递归收敛为必填以便直接渲染。 */
type DeepRequired<T> = T extends readonly (infer U)[]
  ? U[]
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<NonNullable<T[K]>> }
    : T;

type PolicyView = DeepRequired<PolicyConfig>;

/** 放行这些审批项时弹二次确认：一旦放行，破坏性动作不再逐条征求同意。 */
const CONFIRM_ON_ALLOW = new Set(["password_change", "destructive", "payload_exec", "data_mutation"]);

type PolicyConsolePanelProps = {
  /** 有任一审批项仍处于「需人工审批」，用于上层按钮着色。 */
  onGateActiveChange?: (active: boolean) => void;
};

function linesToList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function numbersToList(text: string): number[] {
  return linesToList(text)
    .map((line) => Number.parseInt(line, 10))
    .filter((value) => Number.isFinite(value));
}

function errorMessage(caught: unknown): string {
  if (caught instanceof ApiError && caught.status === 409) {
    return "策略已被其它操作更新，请重新打开面板";
  }
  return caught instanceof Error ? caught.message : "操作失败";
}

function signalsToText(signals: string[]): string {
  return signals.join("\n");
}

/** 策略控制台：风险审批（src-hunt §2）+ 目标范围 + 禁测清单 + 频率并发 + 急停。 */
export function PolicyConsolePanel({ onGateActiveChange }: PolicyConsolePanelProps) {
  const [policy, setPolicy] = useState<PolicyView | null>(null);
  const [draft, setDraft] = useState<PolicyView | null>(null);
  const [gates, setGates] = useState<PolicyApprovalGates | null>(null);
  const [signalDraft, setSignalDraft] = useState<Record<string, string> | null>(null);
  const [revision, setRevision] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const gated = useMemo(() => (gates ? gates.some((item) => !item.allow) : false), [gates]);

  useEffect(() => {
    onGateActiveChange?.(gated);
  }, [gated, onGateActiveChange]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [snapshot, gatesResponse] = await Promise.all([getPolicyConfig(), getPolicyActions()]);
        if (cancelled) return;
        const data = snapshot.data;
        if (data) {
          setPolicy(data.policy as PolicyView);
          setDraft(data.policy as PolicyView);
          setRevision(data.revision);
        }
        const gateData = gatesResponse.data;
        if (gateData) {
          setGates(gateData.approvals);
          setSignalDraft(
            Object.fromEntries(gateData.approvals.map((item) => [item.key, signalsToText(item.signals)])),
          );
          setRevision(gateData.revision);
        }
      } catch (caught) {
        if (!cancelled) setError(errorMessage(caught));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applySnapshot = useCallback((result: { policy: PolicyConfig; revision: number }) => {
    setPolicy(result.policy as PolicyView);
    setDraft(result.policy as PolicyView);
    setRevision(result.revision);
  }, []);

  /** 同步审批项快照；`resetSignals=false` 用于放行切换，避免丢掉未保存的特征编辑。 */
  const applyGates = useCallback(
    (approvals: PolicyApprovalGates, nextRevision: number, resetSignals = true) => {
      setGates(approvals);
      setRevision(nextRevision);
      if (resetSignals) {
        setSignalDraft(
          Object.fromEntries(approvals.map((item) => [item.key, signalsToText(item.signals)])),
        );
      }
    },
    [],
  );

  const patchSection = useCallback(
    <K extends SectionKey>(section: K, patch: Partial<PolicyView[K]>) => {
      setDraft((current) =>
        current ? { ...current, [section]: { ...current[section], ...patch } } : current,
      );
    },
    [],
  );

  const isDirty = useCallback(
    (section: SectionKey) => Boolean(policy && draft && policy[section] !== draft[section]),
    [draft, policy],
  );

  const saveSection = useCallback(
    async (section: SectionKey, label: string) => {
      if (!draft || revision === null) return;
      setBusy(true);
      setError("");
      try {
        const payload = { revision, [section]: draft[section] } as UpdatePolicyConfigRequest;
        const response = await updatePolicyConfig(payload);
        const data = response.data;
        if (data) applySnapshot(data);
        Toast.success(`${label}已保存，立即生效`);
      } catch (caught) {
        setError(errorMessage(caught));
        Toast.error(errorMessage(caught));
      } finally {
        setBusy(false);
      }
    },
    [applySnapshot, draft, revision],
  );

  const toggleGate = useCallback(
    async (key: string, allow: boolean) => {
      if (!gates || busy) return;
      setBusy(true);
      setError("");
      try {
        const payload = {
          approvals: [{ key, allow }],
        } as UpdatePolicyActionsRequest;
        const response = await updatePolicyActions(payload);
        const data = response.data;
        if (data) applyGates(data.approvals, data.revision, false);
        Toast.success(allow ? "已放行，不再逐条征求同意" : "已改为需人工审批");
      } catch (caught) {
        setError(errorMessage(caught));
        Toast.error(errorMessage(caught));
      } finally {
        setBusy(false);
      }
    },
    [applyGates, busy, gates],
  );

  /** 放行破坏性审批项先弹二次确认；收回审批权直接生效。 */
  const requestToggle = useCallback(
    (key: string, allow: boolean) => {
      const item = gates?.find((gate) => gate.key === key);
      if (!allow || !CONFIRM_ON_ALLOW.has(key)) {
        void toggleGate(key, allow);
        return;
      }
      Modal.confirm({
        title: `确认放行「${item?.label ?? key}」？`,
        content: `${item?.description ?? ""}\n放行后这类动作不再逐条征求同意，仅建议在受控环境临时放行。`,
        okText: "确认放行",
        cancelText: "取消",
        onOk: () => void toggleGate(key, allow),
      });
    },
    [gates, toggleGate],
  );

  const dirtySignals = useMemo(
    () =>
      gates && signalDraft
        ? gates.filter((item) => (signalDraft[item.key] ?? "") !== signalsToText(item.signals))
        : [],
    [gates, signalDraft],
  );

  const saveSignals = useCallback(async () => {
    if (!signalDraft || !dirtySignals.length || revision === null) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        revision,
        approvals: dirtySignals.map((item) => ({
          key: item.key,
          signals: linesToList(signalDraft[item.key] ?? ""),
        })),
      } as UpdatePolicyActionsRequest;
      const response = await updatePolicyActions(payload);
      const data = response.data;
      if (data) applyGates(data.approvals, data.revision);
      Toast.success("命中特征已保存，立即生效");
    } catch (caught) {
      setError(errorMessage(caught));
      Toast.error(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }, [applyGates, dirtySignals, revision, signalDraft]);

  const toggleKillSwitch = useCallback(
    async (engaged: boolean) => {
      setBusy(true);
      setError("");
      try {
        const response = await setKillSwitch({ engaged });
        const data = response.data;
        if (data) applySnapshot(data);
        Toast.warning(engaged ? "急停已置位：所有出网动作立即被拒" : "急停已解除");
      } catch (caught) {
        setError(errorMessage(caught));
        Toast.error(errorMessage(caught));
      } finally {
        setBusy(false);
      }
    },
    [applySnapshot],
  );

  if (!draft) {
    return <p className="policy-console-loading">{error || "读取中…"}</p>;
  }

  const frequencyDirty = isDirty("dos") || isDirty("rate_limit");

  return (
    <div className="policy-console">
      {error ? <p className="policy-console-error">{error}</p> : null}

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">风险审批</span>
          <span className="policy-block-note">默认全部需审批</span>
        </header>
        {gates
          ? gates.map((item) => (
              <div className="policy-approval" key={item.key}>
                <div className="policy-row">
                  <span className="policy-row-label">{item.label}</span>
                  <span className={cx("policy-row-state", item.allow ? "is-allow" : "is-gate")}>
                    {item.allow ? "直接放行" : "需审批"}
                  </span>
                  <Switch
                    size="small"
                    checked={item.allow}
                    disabled={busy}
                    onChange={(value) => requestToggle(item.key, value)}
                  />
                </div>
                <p className="policy-approval-desc">{item.description}</p>
              </div>
            ))
          : null}
        <p className="policy-risk-note">
          绝对红线「DoS」同意也不做，恒拦截，不在此提供放行开关。
        </p>
      </section>

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">命中特征</span>
          <Button
            size="small"
            theme={dirtySignals.length ? "solid" : "borderless"}
            type={dirtySignals.length ? "primary" : "tertiary"}
            disabled={busy || !dirtySignals.length}
            onClick={() => void saveSignals()}
          >
            保存
          </Button>
        </header>
        <p className="policy-risk-note">
          命令文本命中即按对应审批项处理；每行一条，大小写不敏感的子串匹配，留空表示不按命令文本判定。
        </p>
        {gates
          ? gates.map((item) => (
              <label className="policy-field" key={item.key}>
                <span className="policy-field-label">{item.label}</span>
                <TextArea
                  value={signalDraft?.[item.key] ?? ""}
                  autosize={{ minRows: 1, maxRows: 6 }}
                  disabled={busy}
                  onChange={(value: string) =>
                    setSignalDraft((current) => ({ ...(current ?? {}), [item.key]: value }))
                  }
                />
              </label>
            ))
          : null}
      </section>

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">目标范围</span>
          <Button
            size="small"
            theme={isDirty("scope") ? "solid" : "borderless"}
            type={isDirty("scope") ? "primary" : "tertiary"}
            disabled={busy || !isDirty("scope")}
            onClick={() => void saveSection("scope", "目标范围")}
          >
            保存
          </Button>
        </header>
        <label className="policy-field">
          <span className="policy-field-label">允许的目标（每行一个；空 = 不限制）</span>
          <TextArea
            value={draft.scope.allowed_hosts.join("\n")}
            autosize={{ minRows: 2, maxRows: 5 }}
            placeholder={"example.com\n*.example.com\n10.0.0.0/24"}
            onChange={(value: string) => patchSection("scope", { allowed_hosts: linesToList(value) })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">允许的端口（每行一个；空 = 不限制）</span>
          <TextArea
            value={draft.scope.allowed_ports.join("\n")}
            autosize={{ minRows: 1, maxRows: 4 }}
            placeholder={"80\n443\n8080"}
            onChange={(value: string) => patchSection("scope", { allowed_ports: numbersToList(value) })}
          />
        </label>
        <div className="policy-row">
          <span className="policy-row-label">禁止访问内网网段</span>
          <span className="policy-row-state" />
          <Switch
            size="small"
            checked={draft.scope.deny_private_ranges}
            disabled={busy}
            onChange={(value) => patchSection("scope", { deny_private_ranges: value })}
          />
        </div>
      </section>

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">禁测清单</span>
          <Button
            size="small"
            theme={isDirty("denylist") ? "solid" : "borderless"}
            type={isDirty("denylist") ? "primary" : "tertiary"}
            disabled={busy || !isDirty("denylist")}
            onClick={() => void saveSection("denylist", "禁测清单")}
          >
            保存
          </Button>
        </header>
        <label className="policy-field">
          <span className="policy-field-label">禁测动作名（每行一个）</span>
          <TextArea
            value={draft.denylist.actions.join("\n")}
            autosize={{ minRows: 1, maxRows: 4 }}
            onChange={(value: string) => patchSection("denylist", { actions: linesToList(value) })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">禁测路径（每行一个，命中即拒）</span>
          <TextArea
            value={draft.denylist.paths.join("\n")}
            autosize={{ minRows: 1, maxRows: 4 }}
            onChange={(value: string) => patchSection("denylist", { paths: linesToList(value) })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">载荷关键词（每行一个，命中即拒）</span>
          <TextArea
            value={draft.denylist.payload_keywords.join("\n")}
            autosize={{ minRows: 1, maxRows: 4 }}
            onChange={(value: string) =>
              patchSection("denylist", { payload_keywords: linesToList(value) })
            }
          />
        </label>
      </section>

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">频率与并发</span>
          <Button
            size="small"
            theme={frequencyDirty ? "solid" : "borderless"}
            type={frequencyDirty ? "primary" : "tertiary"}
            disabled={busy || !frequencyDirty}
            onClick={() => {
              void (async () => {
                await saveSection("rate_limit", "频率限制");
                await saveSection("dos", "并发与总量");
              })();
            }}
          >
            保存
          </Button>
        </header>
        <label className="policy-field">
          <span className="policy-field-label">单目标每分钟请求上限</span>
          <InputNumber
            value={draft.rate_limit.per_target_per_minute}
            min={1}
            disabled={busy}
            onChange={(value) =>
              patchSection("rate_limit", { per_target_per_minute: Number(value) || 1 })
            }
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">全局每分钟请求上限</span>
          <InputNumber
            value={draft.rate_limit.global_per_minute}
            min={1}
            disabled={busy}
            onChange={(value) => patchSection("rate_limit", { global_per_minute: Number(value) || 1 })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">突发额度</span>
          <InputNumber
            value={draft.rate_limit.burst}
            min={1}
            disabled={busy}
            onChange={(value) => patchSection("rate_limit", { burst: Number(value) || 1 })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">单目标并发上限（0 = 不限）</span>
          <InputNumber
            value={draft.dos.max_concurrency_per_target}
            min={0}
            disabled={busy}
            onChange={(value) =>
              patchSection("dos", { max_concurrency_per_target: Number(value) || 0 })
            }
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">总请求量上限（0 = 不限）</span>
          <InputNumber
            value={draft.dos.max_requests_total}
            min={0}
            disabled={busy}
            onChange={(value) => patchSection("dos", { max_requests_total: Number(value) || 0 })}
          />
        </label>
        <label className="policy-field">
          <span className="policy-field-label">单次载荷上限（字节）</span>
          <InputNumber
            value={draft.dos.max_payload_bytes}
            min={1}
            disabled={busy}
            onChange={(value) => patchSection("dos", { max_payload_bytes: Number(value) || 1 })}
          />
        </label>
      </section>

      <section className="policy-block">
        <header className="policy-block-head">
          <span className="policy-block-title">急停开关</span>
          <span className="policy-block-note">置位后所有出网动作立即被拒</span>
        </header>
        <div className="policy-row">
          <span className="policy-row-label">{draft.kill_switch.engaged ? "已置位" : "未置位"}</span>
          <span className={cx("policy-row-state", draft.kill_switch.engaged ? "is-gate" : "is-allow")}>
            {draft.kill_switch.engaged ? "全部拦截中" : "正常运行"}
          </span>
          <Switch
            size="small"
            checked={draft.kill_switch.engaged}
            disabled={busy}
            onChange={(value) => void toggleKillSwitch(value)}
          />
        </div>
      </section>
    </div>
  );
}
