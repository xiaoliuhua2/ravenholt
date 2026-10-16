import { useCallback, useEffect, useRef, useState } from "react";

// 操作台「会话列」宽度与折叠控制：
// - 拖右缘手柄调整宽度并记忆到 localStorage；
// - 折叠按钮可整列收起/展开（折叠状态同样记忆）。
// 未拖拽过宽度时返回 null，交由 CSS 断点（admin.css 的 --admin-context-w）决定默认值。
const STORAGE_KEY = "ravenholt.playground.contextWidth";
const COLLAPSED_KEY = "ravenholt.playground.contextCollapsed";
const MIN_WIDTH = 180;
const MAX_WIDTH = 560;
const COLLAPSED_CLASS = "admin-shell-context-collapsed";

export function useContextColumnWidth() {
  const shellRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState<number | null>(() => {
    const saved = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(saved) && saved >= MIN_WIDTH ? Math.min(saved, MAX_WIDTH) : null;
  });
  const [collapsed, setCollapsed] = useState<boolean>(
    () => window.localStorage.getItem(COLLAPSED_KEY) === "1",
  );

  useEffect(() => {
    const shell = shellRef.current;
    if (!shell) return;
    if (width === null) {
      shell.style.removeProperty("--admin-context-w");
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    shell.style.setProperty("--admin-context-w", `${width}px`);
    window.localStorage.setItem(STORAGE_KEY, String(width));
  }, [width]);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    shellRef.current?.classList.toggle(COLLAPSED_CLASS, collapsed);
  }, [collapsed]);

  const onResizeStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const contextEl = event.currentTarget.parentElement;
    if (!contextEl) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = contextEl.getBoundingClientRect().width;
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);

    const onMove = (moveEvent: PointerEvent) => {
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + (moveEvent.clientX - startX)));
      setWidth(Math.round(next));
    };
    const onUp = (upEvent: PointerEvent) => {
      handle.releasePointerCapture(upEvent.pointerId);
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
      handle.removeEventListener("pointercancel", onUp);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
    handle.addEventListener("pointercancel", onUp);
  }, []);

  const reset = useCallback(() => setWidth(null), []);
  const toggleCollapsed = useCallback(() => setCollapsed((prev) => !prev), []);

  return { shellRef, onResizeStart, reset, collapsed, toggleCollapsed };
}
