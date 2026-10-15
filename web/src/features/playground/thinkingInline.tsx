import type { ReactNode } from "react";

/**
 * 只匹配最常见的两种**内联**标记，且都不跨行：
 * - `**粗体**`（内部不允许再出现 `*`）
 * - `` `行内代码` ``（内部不允许再出现反引号）
 *
 * 刻意不做完整 Markdown：思考文本里常有 `#`、`1.`、`-`、`|`、缩进与代码片段，
 * 交给完整解析器会被误判成标题 / 有序列表 / 表格，反而更难读。
 */
const INLINE_PATTERN = /(\*\*[^*\n]+\*\*|`[^`\n]+`)/g;

/**
 * 把思考正文里的内联标记渲染成元素，其余一律原样保留（含换行与缩进）。
 * 用 React 元素而非 innerHTML，天然免疫注入。
 */
export function renderThinkingInline(text: string): ReactNode {
  if (!text) return text;

  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;

  for (const match of text.matchAll(INLINE_PATTERN)) {
    const token = match[0];
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    if (token.startsWith("**")) {
      nodes.push(
        <strong key={key++} className="thinking-em">
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      nodes.push(
        <code key={key++} className="thinking-code">
          {token.slice(1, -1)}
        </code>,
      );
    }
    last = start + token.length;
  }

  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length ? nodes : text;
}
