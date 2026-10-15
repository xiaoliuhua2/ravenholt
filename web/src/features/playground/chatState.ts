import type {
  AgentContentEvent,
  AgentInputPart,
  SandboxPhase,
} from "../../shared/api/types";
import {
  contentSignature,
  findExecutionBlockIndex,
  hasToolCall,
  transcriptHasEvent,
} from "./transcriptIdentity";
import {
  applyEventToTranscript,
  cloneTranscript,
  createTranscript,
  subagentExecutionItemFromEvent,
} from "./transcriptReducer";
import type {
  AgentTranscript,
  ApprovalNode,
  ChatNode,
  ChatState,
  SandboxNode,
  SubagentExecutionItem,
  ToolExecutionItem,
} from "./transcriptTypes";

export type {
  AgentTranscript,
  ApprovalNode,
  ChatNode,
  ChatState,
  ErrorItem,
  ExecutionItem,
  NestedTranscript,
  StreamingItem,
  SubagentExecutionItem,
  TextItem,
  ThinkingItem,
  ToolExecutionItem,
  TranscriptBlock,
} from "./transcriptTypes";

export const initialChatState: ChatState = { nodes: [], streaming: false, pendingNested: {}, liveFrom: null };

type AgentNode = Extract<ChatNode, { kind: "agent" }>;

function appendUserMessage(
  state: ChatState,
  content: AgentInputPart[],
  displayText: string,
  targetAgentCode: string,
  createdAt: AgentContentEvent["created_at"],
  seq: number,
): ChatState {
  const signature = contentSignature(content);
  if (state.streaming) {
    const existingIndex = findLiveUserMessageIndex(state.nodes, signature, targetAgentCode);
    if (existingIndex !== -1) {
      const existing = state.nodes[existingIndex];
      const liveFrom = state.liveFrom ?? state.nodes.length;
      if (existing.kind !== "user" || !targetAgentCode || existing.targetAgentCode === targetAgentCode) {
        return { ...state, streaming: true, liveFrom };
      }
      const nodes = state.nodes.slice();
      nodes[existingIndex] = { ...existing, targetAgentCode };
      return { ...state, nodes, streaming: true, liveFrom };
    }
  }
  const lastNode = state.nodes[state.nodes.length - 1];
  if (lastNode?.kind === "user" && contentSignature(lastNode.content) === signature) {
    const liveFrom = state.liveFrom ?? state.nodes.length;
    if (!targetAgentCode || lastNode.targetAgentCode === targetAgentCode) {
      return { ...state, streaming: true, liveFrom };
    }
    const nodes = state.nodes.slice();
    nodes[nodes.length - 1] = { ...lastNode, targetAgentCode };
    return { ...state, nodes, streaming: true, liveFrom };
  }
  const nodes = [...state.nodes, {
    kind: "user" as const,
    id: `user:${seq}`,
    createdAt,
    content,
    displayText,
    targetAgentCode,
  }];
  return { ...state, nodes, streaming: true, liveFrom: nodes.length };
}

function findLiveUserMessageIndex(nodes: ChatNode[], signature: string, targetAgentCode: string): number {
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index];
    if (node.kind !== "user") continue;
    if (contentSignature(node.content) !== signature) return -1;
    if (!targetAgentCode || !node.targetAgentCode || node.targetAgentCode === targetAgentCode) {
      return index;
    }
    return -1;
  }
  return -1;
}

export function finishChatTurn(state: ChatState): ChatState {
  return { ...state, streaming: false, liveFrom: null, pendingNested: prunePendingNested(state) };
}

function chatReduce(state: ChatState, event: AgentContentEvent): ChatState {
  return applyContentEvent(state, event);
}

export function chatReplay(events: readonly AgentContentEvent[]): ChatState {
  return finishChatTurn(events.reduce<ChatState>(chatReduce, initialChatState));
}

// Build the rendered node list from a seq-ordered, key-deduped event list.
// The reducer upserts blocks by segment/call/run id, so feeding a clean list
// (one event per logical item) produces a duplicate-free transcript.
export function buildChatNodesFromEvents(events: readonly AgentContentEvent[]): ChatNode[] {
  return chatReplay(events).nodes;
}

function applyContentEvent(state: ChatState, event: AgentContentEvent): ChatState {
  if (event.type === "user_message") {
    return appendUserMessage(state, event.content, event.display_text, event.target_agent_code, event.created_at, event.seq);
  }
  if (event.type === "turn_boundary") {
    return event.nested_call_id ? state : finishChatTurn(state);
  }
  if (event.type === "sandbox") {
    return appendSandboxNode(state, event);
  }
  if (event.type === "approval") {
    return appendApprovalNode(state, event);
  }
  const nestedCallId = "nested_call_id" in event ? event.nested_call_id : "";
  return nestedCallId ? routeToNested(state, event, nestedCallId) : routeToTopLevel(state, event);
}

function routeToTopLevel(state: ChatState, event: AgentContentEvent): ChatState {
  const nodes = state.nodes.slice();
  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];
  let agent: AgentNode;
  if (isWritableAgentTail(state, lastNode, lastIndex)) {
    agent = cloneAgentNode(lastNode);
    if (!agent.createdAt) agent.createdAt = event.created_at;
    nodes[lastIndex] = agent;
  } else {
    const existingIndex = state.streaming ? findLiveAgentForEvent(nodes, state.liveFrom, event) : -1;
    if (existingIndex !== -1) {
      agent = cloneAgentNode(nodes[existingIndex] as AgentNode);
      if (!agent.createdAt) agent.createdAt = event.created_at;
      nodes[existingIndex] = agent;
    } else {
      agent = createAgentNode(event);
      nodes.push(agent);
    }
  }

  const finished = applyEventToTranscript(agent, event);
  const liveFrom = state.liveFrom ?? nodes.length - 1;
  const nextState = finished
    ? finishChatTurn({ ...state, nodes, liveFrom })
    : { ...state, nodes, streaming: true, liveFrom };
  if (event.type === "tool_call" || event.type === "tool_result") {
    return drainPendingNested(nextState, event.call_id);
  }
  // 子代理任务块建立后，把先前按 run_id 排队的子代理流事件补落到位。
  if (event.type === "subagent_task") {
    return drainPendingNested(nextState, event.run_id);
  }
  if (event.type === "error") return clearPendingNested(nextState);
  return nextState;
}

function isWritableAgentTail(state: ChatState, node: ChatNode | undefined, index: number): node is AgentNode {
  return node?.kind === "agent" && state.streaming && state.liveFrom !== null && index >= state.liveFrom;
}

function findLiveAgentForEvent(nodes: ChatNode[], liveFrom: number | null, event: AgentContentEvent): number {
  const start = liveFrom ?? 0;
  for (let index = nodes.length - 1; index >= start; index -= 1) {
    const node = nodes[index];
    if (node.kind !== "agent") continue;
    if (transcriptHasEvent(node, event)) return index;
  }
  return -1;
}

function routeToNested(state: ChatState, event: AgentContentEvent, nestedCallId: string): ChatState {
  const routed = routeToNestedNow(state, event, nestedCallId);
  if (routed) return routed;
  const queued = state.pendingNested[nestedCallId] ?? [];
  return { ...state, pendingNested: { ...state.pendingNested, [nestedCallId]: [...queued, event] } };
}

function routeToNestedNow(state: ChatState, event: AgentContentEvent, nestedCallId: string): ChatState | null {
  if (event.type === "subagent_task") {
    return updateNestedBlock(state, nestedCallId, (block) => {
      if (block.kind === "tool") block.subagentTask = subagentExecutionItemFromEvent(event);
    });
  }
  return updateNestedBlock(state, nestedCallId, (block) => {
    const nested = block.nested ? cloneTranscript(block.nested) : createTranscript(event.created_at);
    if (!nested.createdAt) nested.createdAt = event.created_at;
    applyEventToTranscript(nested, event);
    block.nested = nested;
  });
}

type NestedHostBlock = ToolExecutionItem | SubagentExecutionItem;

// nested_call_id 既能命中父级工具调用（callId），也能命中子代理执行块（runId）——
// strix 路径下子代理的流事件以自身 run_id 作为 nested_call_id 下发。
function updateNestedBlock(state: ChatState, blockId: string, update: (block: NestedHostBlock) => void): ChatState | null {
  const nodes = state.nodes.slice();
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index];
    if (node.kind !== "agent") continue;
    const blockIndex = findExecutionBlockIndex(node.blocks, blockId);
    if (blockIndex === -1) continue;

    const agent = cloneAgentNode(node);
    const block = { ...agent.blocks[blockIndex] } as NestedHostBlock;
    update(block);
    agent.blocks[blockIndex] = block;
    nodes[index] = agent;
    return { ...state, nodes };
  }
  return null;
}

function drainPendingNested(state: ChatState, callId: string): ChatState {
  const pending = state.pendingNested[callId];
  if (!pending?.length) return state;
  let nextState = state;
  const remaining: AgentContentEvent[] = [];
  for (const event of pending) {
    const routed = routeToNestedNow(nextState, event, callId);
    if (routed) nextState = routed;
    else remaining.push(event);
  }
  const pendingNested = { ...nextState.pendingNested };
  if (remaining.length) pendingNested[callId] = remaining;
  else delete pendingNested[callId];
  return { ...nextState, pendingNested };
}

function clearPendingNested(state: ChatState): ChatState {
  return Object.keys(state.pendingNested).length ? { ...state, pendingNested: {} } : state;
}

function prunePendingNested(state: ChatState): ChatState["pendingNested"] {
  if (!Object.keys(state.pendingNested).length) return state.pendingNested;
  const pendingNested: ChatState["pendingNested"] = {};
  for (const [callId, events] of Object.entries(state.pendingNested)) {
    if (!hasToolCall(state.nodes, callId)) pendingNested[callId] = events;
  }
  return pendingNested;
}

// 沙箱生命周期事件在对话流里落成一条独立提示（不并入 agent 气泡）：
// id 取自事件 seq，保证 live 重建与历史重放得到同一个 React key。
function appendSandboxNode(
  state: ChatState,
  event: Extract<AgentContentEvent, { type: "sandbox" }>,
): ChatState {
  const node: SandboxNode = {
    kind: "sandbox",
    id: `sandbox:${event.seq}`,
    createdAt: event.created_at,
    phase: event.phase,
    containerId: event.container_id ?? null,
    containerName: event.container_name,
    containerHash: event.container_hash,
    imageName: event.image_name,
    message: event.message,
  };
  return { ...state, nodes: [...state.nodes, node] };
}

// 审批事件同样落成一条独立提示（不并入 agent 气泡）。与 sandbox 不同，这里按
// ``confirmation_id`` 定位**同一张卡片**：pending → approved/rejected 原地更新，
// 而不是每换一个阶段就多出一条。
function appendApprovalNode(
  state: ChatState,
  event: Extract<AgentContentEvent, { type: "approval" }>,
): ChatState {
  const node: ApprovalNode = {
    kind: "approval",
    id: `approval:${event.confirmation_id}`,
    createdAt: event.created_at,
    confirmationId: event.confirmation_id,
    approvalKey: event.approval_key,
    label: event.label,
    action: event.action,
    target: event.target,
    phase: event.phase,
    message: event.message,
  };
  const index = state.nodes.findIndex(
    (item) => item.kind === "approval" && item.confirmationId === event.confirmation_id,
  );
  if (index === -1) {
    return { ...state, nodes: [...state.nodes, node] };
  }
  const nodes = state.nodes.slice();
  nodes[index] = node;
  return { ...state, nodes };
}

// Node id is derived from the seq of the event that opened the node so the
// full-transcript rebuild on every live flush yields identical React keys
// (no remount/flicker), while still being stable across history replay.
function createAgentNode(event: AgentContentEvent): AgentNode {
  return { kind: "agent", id: `agent:${event.seq}`, ...createTranscript(event.created_at) };
}

function cloneAgentNode(node: AgentNode): AgentNode {
  return { ...node, ...cloneTranscript(node) };
}
