import { Button, Popconfirm, Select, Tag, Toast, Tooltip } from "@douyinfe/semi-ui";
import { Ban, ShieldCheck, ShieldOff, ThumbsUp, Trash2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { showApiError } from "../../shared/api/feedback";
import {
  approvePolicyConfirmation,
  deletePolicyConfirmation,
  queryPolicyConfirmations,
  rejectPolicyConfirmation,
  revokePolicyConfirmation,
} from "../../shared/api/policyConfirmations";
import type { ConfirmationStatus, DecidePolicyConfirmationRequest, PolicyConfirmation } from "../../shared/api/types";
import { OwnerCell, ResourceIdentity, ResourceText, RowActions } from "../../shared/components/ResourceCells";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { formatDateTime } from "../../shared/lib/date";
import {
  AUDIT_CATEGORY_LABEL,
  POLICY_CONFIRMATION_MODE_LABEL,
  POLICY_CONFIRMATION_STATUS_LABEL,
  POLICY_CONFIRMATION_STATUS_COLOR,
  POLICY_CONFIRMATION_STATUSES,
} from "../../shared/lib/labels";
import { UI_TEXT } from "../../shared/lib/uiText";
import { ConfirmationDecisionModal, type ConfirmationDecision } from "./ConfirmationDecisionModal";

type DecisionState = { mode: ConfirmationDecision; confirmation: PolicyConfirmation } | null;

export function PolicyConfirmationsPage() {
  const [statusFilter, setStatusFilter] = useState<ConfirmationStatus | "">("");
  const [decision, setDecision] = useState<DecisionState>(null);
  const [deciding, setDeciding] = useState(false);

  const query = useCallback(
    (params: { page: number; size: number; keyword: string }) => queryPolicyConfirmations({
      page: params.page,
      size: params.size,
      status: statusFilter,
    }),
    [statusFilter],
  );

  const {
    items: confirmations, page, loading, loadItems, total, rangeStart, rangeEnd,
    previous, next, canGoBack, canGoNext, resetPage,
  } = usePagedResourceList<PolicyConfirmation>({ query });

  useAdminResourceHeader({
    refreshLabel: "刷新动作许可",
    loading,
    onRefresh: loadItems,
  });

  const summary = useMemo(
    () => confirmations.reduce(
      (acc, item) => ({ ...acc, [item.status]: acc[item.status] + 1 }),
      { pending: 0, approved: 0, rejected: 0 } as Record<ConfirmationStatus, number>,
    ),
    [confirmations],
  );

  const submitDecision = async (payload: DecidePolicyConfirmationRequest) => {
    if (!decision || deciding) return;
    setDeciding(true);
    try {
      if (decision.mode === "approve") {
        await approvePolicyConfirmation(decision.confirmation.id, payload);
        Toast.success(payload.mode === "always" ? "已批准：长期信任" : "已批准：一次性");
      } else {
        await rejectPolicyConfirmation(decision.confirmation.id, payload);
        Toast.success("已拒绝该动作申请");
      }
      setDecision(null);
    } catch (error) {
      showApiError(error);
    } finally {
      setDeciding(false);
      await loadItems();
    }
  };

  const revokePermit = async (confirmation: PolicyConfirmation) => {
    if (deciding) return;
    setDeciding(true);
    try {
      await revokePolicyConfirmation(confirmation.id);
      Toast.success("已撤销该许可");
    } catch (error) {
      showApiError(error);
    } finally {
      setDeciding(false);
      await loadItems();
    }
  };

  // 删除这条审批记录本身（待办 / 已决 / 已撤销都能删）；审计日志里的决策痕迹不受影响。
  const removeConfirmation = async (confirmation: PolicyConfirmation) => {
    if (deciding) return;
    setDeciding(true);
    try {
      await deletePolicyConfirmation(confirmation.id);
      Toast.success("已删除该审批记录");
    } catch (error) {
      showApiError(error);
    } finally {
      setDeciding(false);
      await loadItems();
    }
  };

  const columns: ResourceColumn<PolicyConfirmation>[] = [
    {
      key: "target", header: "申请动作", width: "minmax(0, 1fr)",
      render: (item) => (
        <ResourceIdentity
          icon={<ShieldCheck size={18} />}
          title={item.target || "-"}
          detail={
            <>
              {item.action || "-"} · {AUDIT_CATEGORY_LABEL[item.category] ?? item.category ?? "-"}
            </>
          }
        />
      ),
    },
    {
      key: "status", header: "状态", width: "96px",
      render: (item) => (
        <Tooltip content={statusDetail(item)}>
          <Tag color={POLICY_CONFIRMATION_STATUS_COLOR[item.status]}>
            {POLICY_CONFIRMATION_STATUS_LABEL[item.status]}
          </Tag>
        </Tooltip>
      ),
    },
    {
      key: "mode", header: "放行方式", width: "minmax(0, 0.66fr)",
      render: (item) => <ResourceText title={modeDetail(item)}>{modeDetail(item)}</ResourceText>,
    },
    {
      key: "decided_by", header: "决策人", width: "minmax(0, 0.5fr)",
      render: (item) => <OwnerCell>{item.decided_by || "-"}</OwnerCell>,
    },
    {
      key: "created", header: "创建时间", width: "168px",
      render: (item) => formatDateTime(item.created_at),
    },
    {
      key: "actions", header: "操作", width: "144px",
      render: (item) => (
        <RowActions>
          {item.status === "pending" ? (
            <>
              <Tooltip content="批准">
                <Button icon={<ThumbsUp size={15} />} theme="borderless" type="primary" disabled={deciding}
                  aria-label={`批准 ${item.target}`}
                  onClick={() => setDecision({ mode: "approve", confirmation: item })}
                />
              </Tooltip>
              <Tooltip content="拒绝">
                <Button icon={<Ban size={15} />} theme="borderless" type="danger" disabled={deciding}
                  aria-label={`拒绝 ${item.target}`}
                  onClick={() => setDecision({ mode: "reject", confirmation: item })}
                />
              </Tooltip>
            </>
          ) : null}
          {item.status === "approved" && !item.revoked_at ? (
            <Popconfirm
              title="撤销许可"
              content={`撤销 ${item.target} 的动作许可？`}
              okType="danger"
              cancelText={UI_TEXT.cancel}
              onConfirm={() => void revokePermit(item)}
            >
              <Button icon={<ShieldOff size={15} />} theme="borderless" type="danger" disabled={deciding}
                aria-label={`撤销 ${item.target} 的动作许可`}
              />
            </Popconfirm>
          ) : null}
          <Popconfirm
            title="删除审批记录"
            content={`删除 ${item.target} 的这条审批记录？（审计日志里的痕迹不受影响）`}
            okType="danger"
            cancelText={UI_TEXT.cancel}
            onConfirm={() => void removeConfirmation(item)}
          >
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger" disabled={deciding}
              aria-label={`删除 ${item.target} 的审批记录`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  return (
    <>
      <ResourcePageShell
        filters={(
          <Select
            prefix={<ShieldCheck size={16} />}
            value={statusFilter}
            optionList={[
              { label: "全部状态", value: "" },
              ...POLICY_CONFIRMATION_STATUSES.map((status) => ({
                label: POLICY_CONFIRMATION_STATUS_LABEL[status],
                value: status,
              })),
            ]}
            onChange={(value) => {
              if (typeof value !== "string") return;
              setStatusFilter(value as ConfirmationStatus | "");
              resetPage();
            }}
          />
        )}
        loading={loading}
        metrics={[
          { label: "当前结果", value: total },
          { label: "待确认", value: summary.pending },
          { label: "已批准", value: summary.approved },
          { label: "已拒绝", value: summary.rejected },
        ]}
        empty={confirmations.length === 0}
        emptyIcon={<ShieldCheck size={42} />}
        emptyTitle="暂无动作许可记录"
        page={page}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        total={total}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<PolicyConfirmation>
          ariaLabel="动作许可"
          columns={columns}
          rows={confirmations}
          rowKey={(item) => item.id}
        />
      </ResourcePageShell>

      <ConfirmationDecisionModal
        open={Boolean(decision)}
        mode={decision?.mode ?? "approve"}
        confirmation={decision?.confirmation ?? null}
        saving={deciding}
        onCancel={() => setDecision(null)}
        onSubmit={submitDecision}
      />
    </>
  );
}

// 放行方式：未决策时为空，决策后叠加生效状态。
function modeDetail(item: PolicyConfirmation): string {
  const parts: string[] = [];
  if (item.mode) parts.push(POLICY_CONFIRMATION_MODE_LABEL[item.mode]);
  if (item.revoked_at) parts.push("已撤销");
  else if (item.consumed_at) parts.push("已消费");
  return parts.length > 0 ? parts.join(" · ") : "-";
}

// 状态悬浮说明：撤销 / 决策时间 / 备注 依次取首个可用信息。
function statusDetail(item: PolicyConfirmation): string | undefined {
  if (item.revoked_at) return `撤销于 ${formatDateTime(item.revoked_at)}`;
  if (item.decided_at) {
    const basis = `决策于 ${formatDateTime(item.decided_at)}`;
    return item.note ? `${basis} · ${item.note}` : basis;
  }
  return item.reason || undefined;
}
