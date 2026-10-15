import { Button, Modal } from "@douyinfe/semi-ui";
import { FormEvent, ReactNode } from "react";
import { UI_TEXT } from "../lib/uiText";

type ResourceModalProps = {
  open: boolean;
  title: string;
  saving: boolean;
  submitLabel: string;
  submitDisabled?: boolean;
  width?: number;
  className?: string;
  /** 可选「次要动作」（如审批弹窗里的「拒绝」），排在取消与主按钮之间。 */
  secondaryAction?: { label: string; disabled?: boolean; onClick: () => void | Promise<void> };
  onCancel: () => void;
  onSubmit: () => void | Promise<void>;
  children: ReactNode;
};

export function ResourceModal({
  open,
  title,
  saving,
  submitLabel,
  submitDisabled = false,
  width = 520,
  className,
  secondaryAction,
  onCancel,
  onSubmit,
  children,
}: ResourceModalProps) {
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await onSubmit();
  };

  return (
    <Modal
      title={title}
      visible={open}
      onCancel={onCancel}
      footer={null}
      width={width}
      maskClosable={!saving}
      className={className}
    >
      <form className="resource-form" onSubmit={handleSubmit}>
        {children}
        <div className="modal-actions">
          <Button type="tertiary" onClick={onCancel} disabled={saving}>{UI_TEXT.cancel}</Button>
          {secondaryAction ? (
            <Button
              type="tertiary"
              theme="borderless"
              disabled={saving || secondaryAction.disabled}
              onClick={() => void secondaryAction.onClick()}
            >
              {secondaryAction.label}
            </Button>
          ) : null}
          <Button htmlType="submit" theme="solid" type="primary" loading={saving} disabled={submitDisabled}>{submitLabel}</Button>
        </div>
      </form>
    </Modal>
  );
}
