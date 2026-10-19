/** 移植自 strix viewer `src/types/events.ts` 的 `ToolRendererProps`（只保留渲染器真正用到的部分）。 */
export interface ToolRendererProps {
  toolName: string;
  args: Record<string, unknown>;
  result: unknown;
  status: "running" | "completed" | "failed" | "error";
  /**
   * 仅当该调用来自用户接入的 MCP 服务器时置位：连接名 + 服务器侧工具名。
   * 平台事件契约里没有该字段，由 `ports.ts` 从 `call_mcp` / `describe_mcp` 的参数推导。
   */
  mcpConnection?: string | null;
  mcpTool?: string | null;
}
