/**
 * 适配层：把平台的工具执行项（`ToolExecutionItem`）翻译成 strix viewer 渲染器
 * 需要的 `ToolRendererProps`。**只做形状转换**，不改变任何后端契约。
 */
import type { ToolExecutionItem } from "../transcriptTypes";
import type { ToolRendererProps } from "./types";

type McpTag = {
  mcpConnection: string | null;
  mcpTool: string | null;
  args: Record<string, unknown>;
};

/**
 * 工具的返回在平台侧是字符串（后端对 dict 会先 `json.dumps`）。
 * viewer 渲染器大多按对象取字段、少数按字符串分支，因此：能解析成 JSON 就用解析值，
 * 否则**原样返回字符串**（比 viewer 原来的 `{__raw}` 包装更贴合这些分支）。
 */
export function coerceResult(output: string): unknown {
  const raw = (output ?? "").trim();
  if (!raw) return null;
  if (!(raw.startsWith("{") || raw.startsWith("[") || raw.startsWith('"'))) return output;
  try {
    return JSON.parse(raw);
  } catch {
    return output;
  }
}

/** 平台状态 → viewer 的 status。使用 `failed`（不用 `error`，渲染器只判 running/failed）。 */
export function toolStatus(item: ToolExecutionItem, live: boolean): ToolRendererProps["status"] {
  if (item.subagentTask?.status === "running") return "running";
  if (!item.resolved) return live ? "running" : "failed";
  return item.isError ? "failed" : "completed";
}

/**
 * 平台事件契约里没有 `mcp_connection` / `mcp_tool` 字段 —— 它们藏在
 * `call_mcp` / `describe_mcp` 的参数里，这里按 viewer 的约定推导出来。
 * 注意：`call_mcp` 的 `arguments` 才是被调工具的真实载荷，需要换到 `args` 上，
 * 否则 McpRenderer 会把"分发参数"当成用户工具入参渲染。
 */
function mcpTag(toolName: string, args: Record<string, unknown>): McpTag | null {
  if (toolName === "call_mcp") {
    const connection = typeof args.connection === "string" ? args.connection.trim() : "";
    const tool = typeof args.tool === "string" ? args.tool.trim() : "";
    const inner = args.arguments;
    return {
      mcpConnection: connection || null,
      mcpTool: tool || null,
      args: inner && typeof inner === "object" ? (inner as Record<string, unknown>) : {},
    };
  }
  if (toolName === "describe_mcp") {
    const connection = typeof args.connection === "string" ? args.connection.trim() : "";
    return { mcpConnection: connection || null, mcpTool: null, args };
  }
  return null;
}

/** 平台默认：工具的入参本来就是 strix 工具 schema 的形状，直接透传即可。 */
function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function toRendererProps(item: ToolExecutionItem, live: boolean): ToolRendererProps {
  const tag = mcpTag(item.name, asRecord(item.arguments));
  return {
    toolName: item.name,
    args: tag ? tag.args : asRecord(item.arguments),
    result: item.resolved ? coerceResult(item.output) : null,
    status: toolStatus(item, live),
    mcpConnection: tag?.mcpConnection ?? null,
    mcpTool: tag?.mcpTool ?? null,
  };
}
