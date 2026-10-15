import { Button } from "@douyinfe/semi-ui";
import { SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cx } from "../../shared/lib/className";
import { PolicyConsolePanel } from "./PolicyConsolePanel";

type PolicyGateControlProps = {
  /** 打开浮层时通知外层，便于关掉其它浮层。 */
  onOpen?: () => void;
};

/** 输入框右下角的策略入口：按钮 + 分组策略控制台浮层。 */
export function PolicyGateControl({ onOpen }: PolicyGateControlProps) {
  const [open, setOpen] = useState(false);
  const [gateActive, setGateActive] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (target && rootRef.current?.contains(target)) return;
      setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const toggleOpen = () => {
    setOpen((current) => {
      const next = !current;
      if (next) onOpen?.();
      return next;
    });
  };

  return (
    <div className="composer-policy-control" ref={rootRef}>
      <Button
        className={cx("composer-action-button", "composer-policy-trigger", gateActive && "is-gated")}
        icon={<SlidersHorizontal size={16} />}
        theme="borderless"
        type={gateActive ? "danger" : "tertiary"}
        onClick={toggleOpen}
        aria-label="风险审批"
        title={gateActive ? "有审批项仍处于需人工审批状态" : "风险审批（src-hunt 红线）"}
      />
      {open ? (
        <div className="composer-policy-popover">
          <PolicyConsolePanel onGateActiveChange={setGateActive} />
        </div>
      ) : null}
    </div>
  );
}
