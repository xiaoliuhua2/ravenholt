/**
 * 一行工具卡片的 strix 原生渲染：图标 + 按工具族分派的 renderer，
 * 外面套 `.rv-scope` 让移植过来的 Tailwind 工具类只作用于这棵子树。
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

import type { ToolExecutionItem } from "../transcriptTypes";
import { getToolIcon, getToolRenderer } from "./index";
import { toRendererProps } from "./ports";

type BoundaryProps = { toolName: string; children: ReactNode };
type BoundaryState = { failed: boolean };

/** 单个 renderer 出错不能白屏：降级成工具名，其余卡片继续渲染。 */
class RendererErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("strix tool renderer failed", this.props.toolName, error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return <span className="text-[13px] text-[#888]">{this.props.toolName}</span>;
    }
    return this.props.children;
  }
}

export function StrixToolRow({ item, live }: { item: ToolExecutionItem; live: boolean }) {
  const props = toRendererProps(item, live);
  const { icon: Icon, color } = getToolIcon(props.toolName, props.mcpConnection);
  const Renderer = getToolRenderer(props.toolName, props.mcpConnection);

  return (
    <div className="rv-scope flex items-start gap-2">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
      <div className="min-w-0 flex-1">
        <RendererErrorBoundary toolName={props.toolName}>
          <Renderer {...props} />
        </RendererErrorBoundary>
      </div>
    </div>
  );
}
