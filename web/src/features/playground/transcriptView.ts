import type {
  AgentTranscript,
  ErrorItem,
  ExecutionItem,
  SubagentExecutionItem,
  TextItem,
  ThinkingItem,
  ToolExecutionItem,
} from "./chatState";

type TranscriptItem = AgentTranscript["blocks"][number];
export type ToolBlock = ToolExecutionItem | SubagentExecutionItem;
export type ContentBlock = TextItem | ErrorItem;
export type TranscriptRenderSegment =
  | { kind: "thinking"; id: string; items: ThinkingItem[] }
  | { kind: "tools"; id: string; items: ToolBlock[] }
  | { kind: "content"; id: string; block: ContentBlock };

// 按 blocks 的原始顺序切段：相邻同类块（思考/工具）聚成一段，正文各自成段。
// 于是思考链、正文、工具调用会按真实发生顺序自然穿插，而不是被全部提到最前面。
export function buildTranscriptSegments(blocks: TranscriptItem[]): TranscriptRenderSegment[] {
  const segments: TranscriptRenderSegment[] = [];

  for (const block of blocks) {
    const last = segments[segments.length - 1];
    if (block.kind === "thinking") {
      if (last?.kind === "thinking") last.items.push(block);
      else segments.push({ kind: "thinking", id: `thinking:${block.id}`, items: [block] });
      continue;
    }
    if (isToolBlock(block)) {
      if (last?.kind === "tools") last.items.push(block);
      else segments.push({ kind: "tools", id: `tools:${block.id}`, items: [block] });
      continue;
    }
    segments.push({ kind: "content", id: `${block.kind}:${block.id}`, block });
  }

  return segments;
}

export function emptyAgentTranscript(): AgentTranscript {
  return {
    createdAt: "",
    agentName: "",
    blocks: [],
  };
}

export function isTranscriptEmpty(transcript: AgentTranscript) {
  return transcript.blocks.length === 0;
}

export function activeThinkingItemId(blocks: TranscriptItem[]) {
  return [...blocks].reverse().find((block): block is ThinkingItem => block.kind === "thinking" && !block.complete)?.id ?? "";
}

/** 本段思考的耗时文案；进行中或时间戳缺失时返回空串（头部不显示）。 */
export function thinkingSegmentDuration(items: ThinkingItem[]): string {
  const startedAt = items.find((item) => item.startedAt)?.startedAt;
  const completedAt = [...items].reverse().find((item) => item.completedAt)?.completedAt;
  if (!startedAt || !completedAt) return "";
  const ms = Date.parse(completedAt) - Date.parse(startedAt);
  if (!Number.isFinite(ms) || ms <= 0) return "";
  if (ms < 1000) return "<1s";
  const seconds = ms / 1000;
  return seconds < 10 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`;
}

/** 折叠态的摘要：最新已完成段落的首行，帮助用户在收起时判断这段在想什么。 */
export function thinkingSegmentSummary(items: ThinkingItem[]): string {
  const latest = [...items].reverse().find((item) => item.complete && item.text.trim());
  const source = (latest ?? items[items.length - 1])?.text ?? "";
  const firstLine = source.trim().split("\n").find((line) => line.trim()) ?? "";
  return firstLine.trim().slice(0, 80);
}

export function activeTextItemId(blocks: TranscriptItem[]) {
  return [...blocks].reverse().find((block): block is TextItem => block.kind === "text" && !block.complete)?.id ?? "";
}

export function transcriptHasRunningExecution(transcript: AgentTranscript): boolean {
  return transcript.blocks.some((block) => isToolBlock(block) && isExecutionRunning(block));
}

export function transcriptItemCount(transcript: AgentTranscript) {
  return transcript.blocks.length;
}

function isToolBlock(block: TranscriptItem): block is ToolBlock {
  return block.kind === "tool" || block.kind === "subagent";
}

function isExecutionRunning(item: ExecutionItem) {
  if (item.kind === "tool") {
    return !item.resolved || item.subagentTask?.status === "running" || Boolean(item.nested && transcriptHasRunningExecution(item.nested));
  }
  return item.status === "running";
}
