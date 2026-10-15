import { Input, Select } from "@douyinfe/semi-ui";
import { Infinity as InfinityIcon, MessageSquare, ShieldCheck, Target, Timer } from "lucide-react";
import { useEffect, useState } from "react";
import type { ConfirmationMode, DecidePolicyConfirmationRequest, PolicyConfirmation } from "../../shared/api/types";
import { ResourceModal } from "../../shared/components/ResourceModal";
import { AUDIT_CATEGORY_LABEL } from "../../shared/lib/labels";

export type ConfirmationDecision = "approve" | "reject";

type ConfirmationDecisionModalProps = {
  open: boolean;
  mode: ConfirmationDecision;
  confirmation: PolicyConfirmation | null;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: DecidePolicyConfirmationRequest) => Promise<void>;
  /** 可选：提供后在「批准」态下额外显示一个「拒绝」次要按钮。 */
  onReject?: () => void | Promise<void>;
};

export function ConfirmationDecisionModal({
  open,
  mode,
  confirmation,
  saving,
  onCancel,
  onSubmit,
  onReject,
}: ConfirmationDecisionModalProps) {
  const [grantMode, setGrantMode] = useState<ConfirmationMode>("once");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) return;
    setGrantMode("once");
    setNote("");
  }, [open]);

  const approving = mode === "approve";

  const submit = async () => {
    await onSubmit({ mode: approving ? grantMode : "once", note: note.trim() });
  };

  return (
    <ResourceModal
      open={open}
      title={approving ? "批准动作许可" : "拒绝动作申请"}
      saving={saving}
      submitLabel={approving ? "批准" : "拒绝"}
      secondaryAction={approving && onReject ? { label: "拒绝", onClick: onReject } : undefined}
      onCancel={onCancel}
      onSubmit={submit}
    >
      <label>
        <span>申请目标</span>
        <div className="confirmation-subject">
          <Target size={15} />
          <div>
            <strong>{confirmation?.target || "-"}</strong>
            <em>
              {confirmation?.action || "-"} ·{" "}
              {AUDIT_CATEGORY_LABEL[confirmation?.category ?? ""] ?? confirmation?.category ?? "-"}
            </em>
          </div>
        </div>
      </label>
      {approving ? (
        <label>
          <span>放行方式</span>
          <Select
            prefix={grantMode === "always" ? <InfinityIcon size={16} /> : <Timer size={16} />}
            value={grantMode}
            optionList={[
              { label: "一次性（命中一次后即失效）", value: "once" },
              { label: "长期信任（长期有效，可随时撤销）", value: "always" },
            ]}
            onChange={(value) => {
              if (typeof value === "string") setGrantMode(value as ConfirmationMode);
            }}
          />
        </label>
      ) : null}
      <label>
        <span>备注</span>
        <Input
          prefix={<MessageSquare size={16} />}
          value={note}
          maxLength={512}
          placeholder={approving ? "可选，记录批准理由" : "可选，记录拒绝理由"}
          onChange={setNote}
        />
      </label>
      <p className="confirmation-hint">
        <ShieldCheck size={13} />
        {approving
          ? "批准后该类动作会按所选方式放行；长期信任可随时在列表里撤销。"
          : "拒绝后该动作仍会被红线拦截，再次触发时会重新生成待确认申请。"}
      </p>
    </ResourceModal>
  );
}
