import type {
  AgentContentEvent,
  AgentInputPart,
  ApprovalPhase,
  SandboxPhase,
  SubagentTaskEvent,
  TextCompleteEvent,
  ThinkingCompleteEvent,
  ToolCallEvent,
  ToolResultEvent,
} from "../../shared/api/types";

export type ThinkingItem = {
  kind: "thinking";
  id: string;
  segmentId: ThinkingCompleteEvent["segment_id"];
  text: ThinkingCompleteEvent["text"];
  complete: boolean;
  /** 首帧到达时刻，用于展示本段思考耗时。 */
  startedAt: string;
  /** 完成帧到达时刻；仍进行中时为空串。 */
  completedAt: string;
};

export type TextItem = {
  kind: "text";
  id: string;
  segmentId: TextCompleteEvent["segment_id"];
  text: TextCompleteEvent["text"];
  complete: boolean;
};

export type ToolExecutionItem = {
  kind: "tool";
  id: string;
  callId: ToolCallEvent["call_id"];
  name: ToolCallEvent["name"];
  arguments: NonNullable<ToolCallEvent["arguments"]>;
  output: ToolResultEvent["output"];
  isError: ToolResultEvent["is_error"];
  resolved: boolean;
  nested?: NestedTranscript;
  subagentTask?: SubagentExecutionItem;
};

export type SubagentExecutionItem = {
  kind: "subagent";
  id: SubagentTaskEvent["run_id"];
  createdAt: SubagentTaskEvent["created_at"];
  runId: SubagentTaskEvent["run_id"];
  parentAgentCode: SubagentTaskEvent["parent_agent_code"];
  parentAgentInstanceId: SubagentTaskEvent["parent_agent_instance_id"];
  agentCode: SubagentTaskEvent["agent_code"];
  /** 子代理展示名（派发时给定）：侧栏标签用它，避免暴露实例 ID。 */
  agentName: SubagentTaskEvent["agent_name"];
  nestedCallId: SubagentTaskEvent["nested_call_id"];
  status: SubagentTaskEvent["status"];
  resultPreview: SubagentTaskEvent["result_preview"];
  errorPreview: SubagentTaskEvent["error_preview"];
  resultChars: SubagentTaskEvent["result_chars"];
  errorChars: SubagentTaskEvent["error_chars"];
  truncated: SubagentTaskEvent["truncated"];
  progress: SubagentTaskEvent["progress"];
  // 子代理自身的思考/正文/工具流：由适配层按 run_id 归集到这里后展示。
  nested?: NestedTranscript;
};

export type ErrorItem = { kind: "error"; id: string; message: string };
export type ExecutionItem = ToolExecutionItem | SubagentExecutionItem;
export type TranscriptBlock = ThinkingItem | TextItem | ExecutionItem | ErrorItem;

export type AgentTranscript = {
  createdAt: AgentContentEvent["created_at"] | "";
  agentName: string;
  blocks: TranscriptBlock[];
};

export type NestedTranscript = AgentTranscript;

export type SandboxNode = {
  kind: "sandbox";
  id: string;
  createdAt: AgentContentEvent["created_at"];
  phase: SandboxPhase;
  containerId: number | null;
  containerName: string;
  containerHash: string;
  imageName: string;
  message: string;
};

export type ApprovalNode = {
  kind: "approval";
  id: string;
  createdAt: AgentContentEvent["created_at"];
  /** 对应 `policy_confirmations` 主键；pending → 终态时按它原地更新同一张卡片。 */
  confirmationId: number;
  approvalKey: string;
  label: string;
  action: string;
  target: string;
  phase: ApprovalPhase;
  message: string;
};

export type ChatNode =
  | {
      kind: "user";
      id: string;
      createdAt: AgentContentEvent["created_at"];
      content: AgentInputPart[];
      displayText: string;
      targetAgentCode: string;
    }
  | ({ kind: "agent"; id: string } & AgentTranscript)
  | SandboxNode
  | ApprovalNode;

export type ChatState = {
  nodes: ChatNode[];
  streaming: boolean;
  pendingNested: Record<string, AgentContentEvent[]>;
  liveFrom: number | null;
};

export type StreamingItem = ThinkingItem | TextItem;
