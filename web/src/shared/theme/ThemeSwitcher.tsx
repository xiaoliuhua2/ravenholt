import { Check, Palette } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cx } from "../lib/className";
import { useTheme } from "./ThemeProvider";
import { THEMES } from "./themes";

type ThemeSwitcherProps = {
  /** 固定在视口右上角（落地页 / 登录页使用） */
  floating?: boolean;
  /** 放在左侧图标窄栏底部，浮层向右上方展开 */
  rail?: boolean;
};

export function ThemeSwitcher({ floating = false, rail = false }: ThemeSwitcherProps) {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const active = THEMES.find((option) => option.id === theme) ?? THEMES[0];

  return (
    <div className={cx("theme-switcher", floating && "theme-switcher-floating", rail && "theme-switcher-rail")} ref={rootRef}>
      <button
        type="button"
        className="theme-switcher-trigger"
        aria-label="切换主题颜色"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Palette size={16} />
        <span className="theme-switcher-dot" style={{ background: active.brand }} />
      </button>

      {open ? (
        <div className="theme-switcher-popover" role="menu" aria-label="主题颜色">
          <div className="theme-switcher-title">主题颜色</div>
          <div className="theme-switcher-grid">
            {THEMES.map((option) => (
              <button
                key={option.id}
                type="button"
                role="menuitemradio"
                aria-checked={option.id === theme}
                className={cx("theme-swatch", option.id === theme && "theme-swatch-active")}
                onClick={() => {
                  setTheme(option.id);
                  setOpen(false);
                }}
              >
                <span className="theme-swatch-dot" style={{ background: option.brand }} />
                <span className="theme-swatch-label">{option.label}</span>
                {option.id === theme ? <Check size={14} /> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
