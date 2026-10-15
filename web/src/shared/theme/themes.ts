// 主题色定义：id 与 themes.css 中的 html[data-theme="..."] 一一对应。
export type ThemeId = "crimson" | "indigo" | "emerald" | "amber" | "violet" | "slate";

export type ThemeOption = {
  id: ThemeId;
  label: string;
  /** 与 themes.css 中的 --z-brand 保持一致，用于色板圆点 */
  brand: string;
};

export const THEMES: ThemeOption[] = [
  { id: "crimson", label: "绯红", brand: "#d92d3a" },
  { id: "indigo", label: "靛蓝", brand: "#4f46e5" },
  { id: "emerald", label: "翡翠", brand: "#059669" },
  { id: "amber", label: "琥珀", brand: "#d97706" },
  { id: "violet", label: "紫罗兰", brand: "#7c3aed" },
  { id: "slate", label: "石墨", brand: "#334155" },
];

export const DEFAULT_THEME: ThemeId = "crimson";

export const THEME_STORAGE_KEY = "ravenholt.theme";

export function isThemeId(value: string | null | undefined): value is ThemeId {
  return THEMES.some((theme) => theme.id === value);
}
