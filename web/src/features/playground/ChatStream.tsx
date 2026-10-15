import { Button, Toast } from "@douyinfe/semi-ui";
import { AtSign, Box, ShieldAlert, Sparkles } from "lucide-react";
import { useCallback, useMemo, useState, type RefObject } from "react";
import { showApiError } from "../../shared/api/feedback";
import { approvePolicyConfirmation, rejectPolicyConfirmation } from "../../shared/api/policyConfirmations";
import type { AgentImageInputPart, AgentInfo, AgentInputPart, DecidePolicyConfirmationRequest } from "../../shared/api/types";
import { useAuth } from "../../shared/auth/AuthProvider";
import { cx } from "../../shared/lib/className";
import { formatDateTime } from "../../shared/lib/date";
import { ImagePreview, imageDataUrl, type ImagePreviewState } from "./ImagePreview";
import type { AgentTranscript, ChatNode } from "./chatState";
import { TranscriptContent } from "./Transcript";
import { emptyAgentTranscript, isTranscriptEmpty } from "./transcriptView";
import type { SubagentSelection } from "./subagentView";

type ChatStreamProps = {
  nodes: ChatNode[];
  streaming: boolean;
  agents: AgentInfo[];
  selectedSubagent: SubagentSelection | null;
  tailRef: RefObject<HTMLDivElement | null>;
  onOpenSubagent: (selection: SubagentSelection) => void;
};

type RenderedChatNode =
  | { kind: "user"; node: Extract<ChatNode, { kind: "user" }>; targetName: string }
  | { kind: "agent"; node: Extract<ChatNode, { kind: "agent" }>; agentName: string; live: boolean }
  | { kind: "sandbox"; node: Extract<ChatNode, { kind: "sandbox" }> }
  | { kind: "approval"; node: Extract<ChatNode, { kind: "approval" }> };

export function ChatStream({
  nodes,
  streaming,
  agents,
  selectedSubagent,
  tailRef,
  onOpenSubagent,
}: ChatStreamProps) {
  const [preview, setPreview] = useState<ImagePreviewState>(null);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((a) => [a.code, a.name])),
    [agents],
  );
  const renderedNodes = useMemo(
    () => buildRenderedChatNodes(nodes, streaming, agentNameByCode),
    [agentNameByCode, nodes, streaming],
  );

  const openImagePreview = (image: AgentImageInputPart, index: number) => {
    setPreview({
      src: imageDataUrl(image),
      alt: `User attachment ${index + 1}`,
    });
  };

  const lastIndex = nodes.length - 1;
  const lastNode = nodes[lastIndex];

  return (
    <div className="chat-stream">
      {nodes.length === 0 ? <ChatEmptyState /> : renderedNodes.map((item) => {
        if (item.kind === "user") {
          return (
            <UserBubble
              key={item.node.id}
              content={item.node.content}
              displayText={item.node.displayText}
              targetName={item.targetName}
              createdAt={item.node.createdAt}
              onPreviewImage={openImagePreview}
            />
          );
        }
        if (item.kind === "sandbox") {
          return <SandboxNotice key={item.node.id} node={item.node} />;
        }
        if (item.kind === "approval") {
          return <ApprovalNotice key={item.node.id} node={item.node} />;
        }
        return (
          <AgentBlock
            key={item.node.id}
            agentName={item.agentName}
            transcript={item.node}
            live={item.live}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
        );
      })}
      {streaming && lastNode?.kind === "user" ? (
        <AgentBlock
          key="pending-agent"
          agentName={resolveAgentName(agentNameByCode, lastNode.targetAgentCode)}
          transcript={emptyAgentTranscript()}
          live
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      ) : null}
      <div ref={tailRef} className="chat-tail" />
      <ImagePreview preview={preview} onClose={() => setPreview(null)} />
    </div>
  );
}

function SandboxNotice({ node }: { node: Extract<ChatNode, { kind: "sandbox" }> }) {
  const label = node.phase === "ready"
    ? (node.containerName ? `沙箱已就绪 · ${node.containerName}` : "沙箱已就绪")
    : (node.message || "正在准备沙箱环境");
  return (
    <div className="chat-sandbox-notice">
      <Box size={14} />
      <span>{label}</span>
      {node.containerHash ? <small>{node.containerHash.slice(0, 12)}</small> : null}
    </div>
  );
}

const APPROVAL_PHASE_LABEL: Record<string, string> = {
  pending: "待确认",
  approved: "已批准",
  rejected: "已拒绝",
  timeout: "已超时",
  cancelled: "已作废",
};

/** 风险审批卡片：命中未放行的审批项时出现，用户可直接在对话流里决定是否执行。
 *
 * 阶段变化由后端推同一条确认的新事件驱动（时间线 key 为 `approval:<id>`），
 * 因此这里不做本地乐观更新，只负责发决策与提示。
 * 审批接口仅管理员可调，非管理员只读提示（避免点了才吃 403）。 */
function ApprovalNotice({ node }: { node: Extract<ChatNode, { kind: "approval" }> }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const pending = node.phase === "pending";
  const canDecide = user?.role === "admin";

  const decide = useCallback(
    async (approve: boolean) => {
      if (busy) return;
      setBusy(true);
      try {
        const payload: DecidePolicyConfirmationRequest = { mode: "once", note: "" };
        if (approve) {
          await approvePolicyConfirmation(node.confirmationId, payload);
          Toast.success("已批准，本次动作将继续执行");
        } else {
          await rejectPolicyConfirmation(node.confirmationId, payload);
          Toast.success("已拒绝，本次动作不会执行");
        }
      } catch (error) {
        showApiError(error);
      } finally {
        setBusy(false);
      }
    },
    [busy, node.confirmationId],
  );

  return (
    <div className={cx("chat-approval-card", `is-${node.phase}`)}>
      <div className="chat-approval-head">
        <ShieldAlert size={14} />
        <span className="chat-approval-title">
          {pending ? "需要你确认才执行" : APPROVAL_PHASE_LABEL[node.phase] ?? node.phase}
        </span>
        {node.label ? <span className="chat-approval-tag">{node.label}</span> : null}
      </div>
      <div className="chat-approval-body">
        <code>{node.action}</code>
        {node.target ? <span className="chat-approval-target">{node.target}</span> : null}
      </div>
      {node.message ? <p className="chat-approval-message">{node.message}</p> : null}
      {pending && canDecide ? (
        <div className="chat-approval-actions">
          <Button size="small" type="primary" theme="solid" loading={busy} onClick={() => void decide(true)}>
            批准执行
          </Button>
          <Button size="small" type="tertiary" theme="borderless" disabled={busy} onClick={() => void decide(false)}>
            拒绝
          </Button>
        </div>
      ) : null}
      {pending && !canDecide ? (
        <p className="chat-approval-message">该动作需要管理员在「策略审批」中确认后才会执行。</p>
      ) : null}
    </div>
  );
}

function ChatEmptyState() {
  return (
    <div className="chat-empty">
      <div className="chat-empty-mark">
        <Sparkles size={28} />
      </div>
      <h2>开始新的对话</h2>
      <p>
        向安全运营智能体提出任何问题
        <br />
        —— 渗透测试、代码审计或威胁研判。
      </p>
    </div>
  );
}

function buildRenderedChatNodes(
  nodes: ChatNode[],
  streaming: boolean,
  agentNameByCode: Map<string, string>,
): RenderedChatNode[] {
  const rendered: RenderedChatNode[] = [];
  const lastIndex = nodes.length - 1;
  let lastTargetName = "";

  nodes.forEach((node, index) => {
    if (node.kind === "user") {
      lastTargetName = resolveAgentName(agentNameByCode, node.targetAgentCode);
      rendered.push({ kind: "user", node, targetName: lastTargetName });
      return;
    }
    if (node.kind === "sandbox") {
      rendered.push({ kind: "sandbox", node });
      return;
    }
    if (node.kind === "approval") {
      rendered.push({ kind: "approval", node });
      return;
    }

    const live = streaming && index === lastIndex;
    if (!live && isTranscriptEmpty(node)) return;
    rendered.push({ kind: "agent", node, agentName: node.agentName || lastTargetName, live });
  });

  return rendered;
}

function MessageTimestamp({ value }: { value: string }) {
  return <time className="message-timestamp" dateTime={value}>{formatDateTime(value)}</time>;
}

function resolveAgentName(agentNameByCode: Map<string, string>, agentCode: string) {
  return agentNameByCode.get(agentCode) ?? agentCode;
}

function UserBubble({
  content,
  displayText,
  targetName,
  createdAt,
  onPreviewImage,
}: {
  content: AgentInputPart[];
  displayText: string;
  targetName: string;
  createdAt: string;
  onPreviewImage: (image: AgentImageInputPart, index: number) => void;
}) {
  const textParts = content.filter((part): part is Extract<AgentInputPart, { type: "text" }> => part.type === "text");
  const imageParts = content.filter((part): part is AgentImageInputPart => part.type === "image");
  return (
    <div className="chat-row chat-row-user">
      <div className="chat-message chat-message-user">
        <MessageTimestamp value={createdAt} />
        <div className="user-bubble">
          {targetName ? (
            <span className="user-bubble-mention">
              <AtSign size={11} />
              <span>{targetName}</span>
            </span>
          ) : null}
          {textParts.length ? (
            <span className="user-bubble-text">{textParts.map((part) => part.text).join("\n\n")}</span>
          ) : displayText ? (
            <span className="user-bubble-text">{displayText}</span>
          ) : null}
          {imageParts.length ? (
            <div className="user-bubble-images">
              {imageParts.map((part, index) => (
                <button
                  key={`${part.media_type}:${index}:${part.data.length}`}
                  type="button"
                  className="user-bubble-image-button"
                  onClick={() => onPreviewImage(part, index)}
                  aria-label={`Preview attachment ${index + 1}`}
                >
                  <img
                    className="user-bubble-image"
                    src={imageDataUrl(part)}
                    alt="用户附件"
                  />
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function AgentBlock({
  agentName,
  transcript,
  live,
  selectedSubagent,
  onOpenSubagent,
}: {
  agentName: string;
  transcript: AgentTranscript;
  live: boolean;
  selectedSubagent: SubagentSelection | null;
  onOpenSubagent: (selection: SubagentSelection) => void;
}) {
  return (
    <div className="chat-row chat-row-agent">
      <div className="agent-block">
        <div className="agent-header">
          {agentName ? <span>{agentName}</span> : null}
          {live ? <span className="agent-pulse" /> : null}
          {transcript.createdAt ? <MessageTimestamp value={transcript.createdAt} /> : null}
        </div>
        <TranscriptContent
          transcript={transcript}
          live={live}
          pendingEmpty
          selectedSubagent={selectedSubagent}
          onOpenSubagent={onOpenSubagent}
        />
      </div>
    </div>
  );
}
