import type { AgentContentEvent, SubagentTaskEvent } from "../../shared/api/types";
import { createClientId } from "../../shared/lib/id";
import {
  findCompletedTextIndex,
  findStreamingBlockIndex,
  findToolBlockIndex,
  hasCoveredCompletedText,
} from "./transcriptIdentity";
import type {
  AgentTranscript,
  StreamingItem,
  SubagentExecutionItem,
  ThinkingItem,
  ToolExecutionItem,
  TranscriptBlock,
} from "./transcriptTypes";

export function applyEventToTranscript(transcript: AgentTranscript, event: AgentContentEvent): boolean {
  switch (event.type) {
    case "user_message":
    case "turn_boundary":
      return false;
    case "thinking_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "thinking", event.segment_id, { text: event.text, at: event.created_at });
      return false;
    case "thinking_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "thinking", event.segment_id, { text: event.text, complete: true, at: event.created_at });
      return false;
    case "text_delta":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "text", event.segment_id, { text: event.text });
      return false;
    case "text_complete":
      setAgentName(transcript, event.agent_name);
      upsertStreamingBlock(transcript.blocks, "text", event.segment_id, { text: event.text, complete: true });
      return false;
    case "tool_call":
      setAgentName(transcript, event.agent_name);
      upsertToolCall(transcript.blocks, event.call_id, event.name, event.arguments ?? {});
      return false;
    case "tool_result":
      setAgentName(transcript, event.agent_name);
      upsertToolResult(transcript.blocks, event.call_id, event.output, event.is_error);
      return false;
    case "subagent_task":
      setAgentName(transcript, event.agent_name);
      upsertSubagentTask(transcript.blocks, subagentExecutionItemFromEvent(event));
      return false;
    case "sandbox":
      // 沙箱生命周期不落进对话正文；由会话级状态（顶栏沙箱卡片）消费。
      return false;
    case "approval":
      // 审批卡片同样不落进 agent 气泡正文；由对话流的独立节点承载。
      return false;
    case "error":
      setAgentName(transcript, event.agent_name);
      transcript.blocks.push({ kind: "error", id: `error:${event.seq}:${event.created_at}`, message: event.message || "agent run failed" });
      return true;
  }
}

export function createTranscript(createdAt: AgentContentEvent["created_at"] | "" = ""): AgentTranscript {
  return { createdAt, agentName: "", blocks: [] };
}

export function cloneTranscript(transcript: AgentTranscript): AgentTranscript {
  return { createdAt: transcript.createdAt, agentName: transcript.agentName, blocks: transcript.blocks.slice() };
}

function setAgentName(transcript: AgentTranscript, name: string) {
  if (name && !transcript.agentName) transcript.agentName = name;
}

function upsertStreamingBlock(
  blocks: TranscriptBlock[],
  kind: StreamingItem["kind"],
  segmentId: string,
  patch: { text: string; complete?: boolean; at?: string },
) {
  const at = patch.at ?? "";
  const index = findStreamingBlockIndex(blocks, kind, segmentId);
  if (index === -1) {
    if (hasCoveredCompletedText(blocks, kind, patch.text)) return;
    if (kind === "thinking") {
      blocks.push({
        kind,
        id: `${kind}:${segmentId}`,
        segmentId,
        text: patch.text,
        complete: Boolean(patch.complete),
        // 首帧时间与完成时间用于展示本段思考耗时；未传时留空，UI 自动隐藏。
        startedAt: at,
        completedAt: patch.complete ? at : "",
      });
      return;
    }
    blocks.push({ kind, id: `${kind}:${segmentId}`, segmentId, text: patch.text, complete: Boolean(patch.complete) } as StreamingItem);
    return;
  }
  if (kind === "thinking") {
    const existing = blocks[index] as ThinkingItem;
    const duplicateIndex = findCompletedTextIndex(blocks, kind, patch.text, index);
    if (duplicateIndex !== -1) {
      blocks.splice(index, 1);
      return;
    }
    if (existing.complete && existing.text === patch.text) return;
    blocks[index] = {
      ...existing,
      text: patch.text,
      complete: patch.complete ?? existing.complete,
      startedAt: existing.startedAt || at,
      completedAt: patch.complete ? (existing.completedAt || at) : existing.completedAt,
    };
    return;
  }
  const existing = blocks[index] as StreamingItem;
  const duplicateIndex = findCompletedTextIndex(blocks, kind, patch.text, index);
  if (duplicateIndex !== -1) {
    blocks.splice(index, 1);
    return;
  }
  if (existing.complete && existing.text === patch.text) return;
  blocks[index] = {
    ...existing,
    text: patch.text,
    complete: patch.complete ?? existing.complete,
  };
}

function upsertToolCall(blocks: TranscriptBlock[], callId: string, name: string, argumentsValue: Record<string, unknown>) {
  // A nameless tool call is not renderable; drop it so it never reaches the UI.
  if (!name) return;
  const index = findToolBlockIndex(blocks, callId, name, argumentsValue);
  if (index === -1) {
    blocks.push({ kind: "tool", id: callId || createClientId("transcript"), callId, name, arguments: argumentsValue, output: "", isError: false, resolved: false });
    return;
  }
  const existing = blocks[index] as ToolExecutionItem;
  blocks[index] = { ...existing, callId: existing.callId || callId, name, arguments: argumentsValue };
}

function upsertToolResult(blocks: TranscriptBlock[], callId: string, output: string, isError: boolean) {
  // Attach to its named tool call; never materialize an orphan (nameless) block.
  const index = findToolBlockIndex(blocks, callId);
  if (index === -1) return;
  const existing = blocks[index] as ToolExecutionItem;
  blocks[index] = { ...existing, output, isError, resolved: true };
}

function upsertSubagentTask(blocks: TranscriptBlock[], nextItem: SubagentExecutionItem) {
  const index = blocks.findIndex((block) => block.kind === "subagent" && block.runId === nextItem.runId);
  if (index === -1) {
    blocks.push(nextItem);
    return;
  }
  // 状态更新事件必须保留已归集的子代理思考/正文流，否则每次进度轮询都会把它清空。
  const existing = blocks[index] as SubagentExecutionItem;
  blocks[index] = { ...nextItem, nested: existing.nested ?? nextItem.nested };
}

export function subagentExecutionItemFromEvent(event: SubagentTaskEvent): SubagentExecutionItem {
  return {
    kind: "subagent",
    id: event.run_id,
    createdAt: event.created_at,
    runId: event.run_id,
    parentAgentCode: event.parent_agent_code,
    parentAgentInstanceId: event.parent_agent_instance_id,
    agentCode: event.agent_code,
    agentName: event.agent_name,
    nestedCallId: event.nested_call_id,
    status: event.status,
    resultPreview: event.result_preview,
    errorPreview: event.error_preview,
    resultChars: event.result_chars,
    errorChars: event.error_chars,
    truncated: event.truncated,
    progress: event.progress,
  };
}
