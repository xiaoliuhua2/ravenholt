// 统一用中文紧凑格式（如 2026/10/11 21:13）：
//   1) 中文界面里不该出现 "Oct 11, 2026, 09:13 PM" 这种英文日期；
//   2) 紧凑格式宽度约 115px，小于列宽下限 150px，避免窄屏下日期文字溢出格子、
//      压到相邻的「更新时间」列。
// 格式化器提到模块级复用，避免每行渲染都新建 Intl 实例。
const dateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDateTime(value: string) {
  return dateTimeFormatter.format(new Date(value));
}
