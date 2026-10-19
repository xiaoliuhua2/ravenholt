"use client";

import { MarkdownRenderer } from "../MarkdownRenderer";

interface MarkdownProps {
  text: string;
  className?: string;
}

/**
 * 移植自 strix viewer 的 Markdown 展示组件：只保留原有 props 形状，
 * 渲染交给平台自己的 MarkdownRenderer（已含 remark-gfm / remark-breaks / Mermaid）。
 */
export default function Markdown({ text, className = "" }: MarkdownProps) {
  return (
    <div className={className}>
      <MarkdownRenderer markdown={text} />
    </div>
  );
}
