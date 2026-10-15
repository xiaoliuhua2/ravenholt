import { Button, Tag, Toast, Tooltip } from "@douyinfe/semi-ui";
import { Activity, Box, FolderKanban, FolderOpen, PanelRightOpen, Plus, Radar } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAdminHeaderActions } from "../../app/layouts/AdminLayout";
import { showApiError } from "../../shared/api/feedback";
import { SANDBOX_CONTAINER_STATUS } from "../../shared/api/generated/constants";
import { approvePolicyConfirmation, queryPolicyConfirmations, rejectPolicyConfirmation } from "../../shared/api/policyConfirmations";
import { buildContainerCaidoUrl, canOpenContainerCaido, queryAvailableSandboxContainers } from "../../shared/api/sandboxContainers";
import type {
  AgentInputPart,
  DecidePolicyConfirmationRequest,
  PolicyConfirmation,
  SandboxContainer,
} from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import { SANDBOX_CONTAINER_STATUS_COLOR, SANDBOX_CONTAINER_STATUS_LABEL } from "../../shared/lib/labels";
import { useContainerShell } from "../container-shell/ContainerShellProvider";
import { ConfirmationDecisionModal } from "../policy-confirmations/ConfirmationDecisionModal";
import { WorkProjectInfoModal } from "../work-projects/WorkProjectInfoModal";
import { useAgentSessionContext } from "./AgentSessionProvider";
import { ChatStream } from "./ChatStream";
import type { ChatNode } from "./chatState";
import { Composer } from "./Composer";
import { MessageScrollPanel } from "./MessageScrollPanel";
import { SubagentSidePanel } from "./SubagentSidePanel";
import { useSubagentPanel } from "./useSubagentPanel";
import { loadWorkProjectRecordSnapshot } from "../work-projects/workProjectRecords";

type PlaygroundLocationState = { sessionId?: string };

type SandboxActionButtonProps = {
  ariaLabel: string;
  disabled: boolean;
  icon: ReactNode;
  tooltip: string;
  onClick: () => void;
};

const STATUS_LABEL: Record<string, string> = {
  open: "在线",
  connecting: "连接中",
  closed: "已断开",
  idle: "空闲",
};

// 「项目记录」红点：轮询项目发现数，与本地记录的「上次已看过的数量」比较。
const PROJECT_FINDINGS_POLL_MS = 20000;
const PROJECT_FINDINGS_SEEN_KEY = (projectId: number) => `ravenholt:project-findings-seen:${projectId}`;

/** 读取「该项目上次已被查看的发现数」；从未记录过返回 null。 */
function readSeenFindings(projectId: number): number | null {
  try {
    const raw = window.localStorage.getItem(PROJECT_FINDINGS_SEEN_KEY(projectId));
    if (raw === null) return null;
    const value = Number.parseInt(raw, 10);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function writeSeenFindings(projectId: number, count: number): void {
  try {
    window.localStorage.setItem(PROJECT_FINDINGS_SEEN_KEY(projectId), String(count));
  } catch {
    // 本地存储不可用（隐私模式等）时忽略：红点只是辅助提示
  }
}

export function PlaygroundPage() {
  const setHeaderActions = useAdminHeaderActions();
  const {
    activeSessionId, activeSessionSummary, selectSession,
    chatState, status, historyLoading, historyHasMore, historyPrepending, historyVersion,
    agents, defaultAgentCode, activeAgentCode, setActiveAgentCode,
    send, interrupt, cancelAll, loadPreviousHistory,
  } = useAgentSessionContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [sandboxContainers, setSandboxContainers] = useState<SandboxContainer[]>([]);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [projectRecordsOpen, setProjectRecordsOpen] = useState(false);
  const { openFileManager, syncContainerWindows } = useContainerShell();
  const { selectedSubagent, setSelectedSubagent, subagentTabs, closeSubagentPanel } = useSubagentPanel(chatState, activeSessionId);
  const hasRunningSubagents = subagentTabs.some((tab) => tab.status === "running");
  const agentSwitchDisabled = activeAgentCode === defaultAgentCode && hasRunningSubagents;

  // 沙箱由运行时按会话自动 provision（provision → 回写会话 runtime_sandbox_container_id）。
  // 前端不再让用户挑容器，只负责展示"当前沙箱"并据此提供入口。
  const currentSandboxId = activeSessionSummary?.runtime_sandbox_container_id ?? null;
  const currentSandbox = useMemo(
    () => sandboxContainers.find((container) => container.id === currentSandboxId) ?? null,
    [currentSandboxId, sandboxContainers],
  );
  const currentSandboxName = currentSandbox?.container_name ?? "当前沙箱";
  const sandboxPreparing = Boolean(activeSessionId) && currentSandboxId === null && chatState.streaming;
  const filesUnavailableReason = describeFilesUnavailable(currentSandbox);
  const activeProjectId = activeSessionSummary?.session_type === "project" ? activeSessionSummary.project_id ?? null : null;
  const [projectFindingsCount, setProjectFindingsCount] = useState(0);
  const [seenProjectFindings, setSeenProjectFindings] = useState(0);
  const hasNewFindings = activeProjectId !== null && projectFindingsCount > seenProjectFindings;

  const markProjectFindingsSeen = useCallback(() => {
    if (activeProjectId === null || projectFindingsCount <= 0) return;
    writeSeenFindings(activeProjectId, projectFindingsCount);
    setSeenProjectFindings(projectFindingsCount);
  }, [activeProjectId, projectFindingsCount]);

  const openProjectRecords = useCallback(() => {
    setProjectRecordsOpen(true);
    markProjectFindingsSeen();
  }, [markProjectFindingsSeen]);
  const openSubagentPanel = useCallback(() => {
    const tab = [...subagentTabs].reverse().find((item) => item.status === "running") ?? subagentTabs[subagentTabs.length - 1];
    if (tab) setSelectedSubagent(tab.agentCode);
  }, [setSelectedSubagent, subagentTabs]);

  const openCurrentFileManager = useCallback(() => {
    if (currentSandbox) openFileManager(currentSandbox);
  }, [openFileManager, currentSandbox]);

  // 轮询当前项目的发现数；与本地「上次已看过」比较 → 有新报告则亮红点。
  // 首次见到某项目时以当前数量为基线，避免一进来就误报「有新报告」。
  useEffect(() => {
    if (activeProjectId === null) {
      setProjectFindingsCount(0);
      setSeenProjectFindings(0);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const snapshot = await loadWorkProjectRecordSnapshot(activeProjectId);
        if (cancelled) return;
        const count = snapshot.records.findings.length;
        setProjectFindingsCount(count);
        // 没有「已读」记录 = 从没看过该项目 → 视作 0，让**既有但未查看**的发现也能亮红点；
        // 只有真正打开过项目记录才会写入已读数（见 markProjectFindingsSeen）。
        setSeenProjectFindings(readSeenFindings(activeProjectId) ?? 0);
      } catch (error) {
        // 红点属辅助信息：失败不打断主流程，但要留痕便于排查（曾因静默吞错导致点"消失"）
        console.warn("[项目记录红点] 拉取项目发现数失败", error);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), PROJECT_FINDINGS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeProjectId]);

  // 项目记录面板开着时持续视为「已看」：面板里正在滚动查看的新发现不应再亮红点。
  useEffect(() => {
    if (projectRecordsOpen) markProjectFindingsSeen();
  }, [projectRecordsOpen, markProjectFindingsSeen]);

  // 命中未放行审批项时，后端会往本会话推一条 approval 事件。这里**主动弹出模态**并给出
  // 「批准 / 拒绝」两个按钮——只靠对话流里的小卡片容易被漏掉。批准后命令会在
  // approval_wait_seconds 内继续执行，不会打断本次测试。
  const pendingApproval = useMemo(() => {
    const approvals = chatState.nodes.filter(
      (node): node is Extract<ChatNode, { kind: "approval" }> =>
        node.kind === "approval" && node.phase === "pending",
    );
    return approvals.length ? approvals[approvals.length - 1] : null;
  }, [chatState.nodes]);
  const [approvalModalId, setApprovalModalId] = useState<number | null>(null);
  const [approvalRecord, setApprovalRecord] = useState<PolicyConfirmation | null>(null);
  const [approvalSaving, setApprovalSaving] = useState(false);
  const autoShownApprovals = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!pendingApproval) return;
    const id = pendingApproval.confirmationId;
    if (autoShownApprovals.current.has(id)) return; // 同一条只自动弹一次
    autoShownApprovals.current.add(id);
    setApprovalModalId(id);
  }, [pendingApproval]);

  useEffect(() => {
    if (approvalModalId === null) return;
    let cancelled = false;
    void (async () => {
      try {
        const response = await queryPolicyConfirmations({ page: 1, size: 50, status: "pending" });
        if (cancelled) return;
        setApprovalRecord((response.data?.items ?? []).find((item) => item.id === approvalModalId) ?? null);
      } catch {
        // 拿不到详情不影响决策按钮：模态用事件里的字段兜底展示
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [approvalModalId]);

  const decideApproval = useCallback(
    async (approve: boolean, payload: DecidePolicyConfirmationRequest) => {
      if (approvalModalId === null || approvalSaving) return;
      setApprovalSaving(true);
      try {
        if (approve) await approvePolicyConfirmation(approvalModalId, payload);
        else await rejectPolicyConfirmation(approvalModalId, payload);
        Toast.success(approve ? "已批准，本次动作将继续执行" : "已拒绝，本次动作不会执行");
        setApprovalModalId(null);
      } catch (error) {
        showApiError(error);
      } finally {
        setApprovalSaving(false);
      }
    },
    [approvalModalId, approvalSaving],
  );

  const loadSandboxes = useCallback(async () => {
    setSandboxLoading(true);
    try {
      const response = await queryAvailableSandboxContainers({ page: 1, size: 100, keyword: "" });
      setSandboxContainers(response.data?.items ?? []);
    } catch (error) {
      showApiError(error);
    } finally {
      setSandboxLoading(false);
    }
  }, []);

  // consume sessionId from navigate state (e.g. project "Go") then clear so
  // back-navigation does not retrigger the jump
  useEffect(() => {
    const incoming = (location.state as PlaygroundLocationState | null)?.sessionId;
    if (incoming) {
      selectSession(incoming);
      navigate(location.pathname, { replace: true });
    }
  }, [location.pathname, location.state, navigate, selectSession]);

  useEffect(() => {
    void loadSandboxes();
  }, [loadSandboxes]);

  // 运行时就绪后会话摘要才会带上容器 id；列表里若还没有它，补拉一次以拿到详情。
  useEffect(() => {
    if (currentSandboxId === null) return;
    if (sandboxContainers.some((container) => container.id === currentSandboxId)) return;
    void loadSandboxes();
  }, [currentSandboxId, sandboxContainers, loadSandboxes]);

  useEffect(() => {
    syncContainerWindows(currentSandbox);
  }, [
    activeSessionId,
    currentSandbox?.id,
    currentSandbox?.control_proxy_host_port,
    currentSandbox?.status,
  ]);

  const headerNode = useMemo(() => (
    <>
      <SandboxStatusChip
        className="sandbox-selector-topbar"
        loading={sandboxLoading && sandboxContainers.length === 0 && Boolean(activeSessionId)}
        preparing={sandboxPreparing}
        sandbox={currentSandbox}
      />
      <div className="sandbox-container-actions" aria-label="沙箱操作">
        {activeProjectId ? (
          <span className="sandbox-action-badge-wrap">
            <SandboxActionButton
              ariaLabel={hasNewFindings ? "打开项目记录（有新的发现/报告）" : "打开项目记录"}
              disabled={false}
              icon={<FolderKanban size={15} />}
              tooltip={hasNewFindings ? "项目记录 · 有新的发现/报告" : "项目记录"}
              onClick={openProjectRecords}
            />
            {hasNewFindings ? <i className="sandbox-action-dot" aria-hidden="true" /> : null}
          </span>
        ) : null}
        <SandboxActionButton
          ariaLabel="打开子智能体面板"
          disabled={subagentTabs.length === 0}
          icon={<PanelRightOpen size={15} />}
          tooltip={subagentTabs.length > 0 ? "打开子智能体面板" : "暂无子智能体消息"}
          onClick={openSubagentPanel}
        />
        <SandboxActionButton
          ariaLabel={`浏览 ${currentSandboxName} 的文件`}
          disabled={Boolean(filesUnavailableReason)}
          icon={<FolderOpen size={15} />}
          tooltip={filesUnavailableReason ?? `浏览 ${currentSandboxName} 的文件`}
          onClick={openCurrentFileManager}
        />
        <SandboxActionButton
          ariaLabel={`打开 ${currentSandboxName} 的抓包界面`}
          disabled={!currentSandbox || !canOpenContainerCaido(currentSandbox)}
          icon={<Radar size={15} />}
          tooltip={currentSandbox && canOpenContainerCaido(currentSandbox)
            ? `打开 ${currentSandboxName} 的抓包界面`
            : "当前沙箱尚未暴露抓包端口"}
          onClick={() => {
            if (!currentSandbox) return;
            try {
              window.open(buildContainerCaidoUrl(currentSandbox), "_blank", "noopener,noreferrer");
            } catch (error) {
              showApiError(error);
            }
          }}
        />
      </div>
      <Button icon={<Plus size={16} />} theme="solid" type="primary" onClick={() => selectSession(null)}>
        新建对话
      </Button>
      <span className={cx("stream-status", `stream-status-${status}`)}>
        <Activity size={14} />
        <span>{STATUS_LABEL[status] ?? "空闲"}</span>
      </span>
    </>
  ), [activeProjectId, currentSandbox, currentSandboxName, filesUnavailableReason, hasNewFindings, openCurrentFileManager, openProjectRecords, openSubagentPanel, sandboxContainers.length, sandboxLoading, sandboxPreparing, selectSession, status, subagentTabs.length]);

  useLayoutEffect(() => {
    setHeaderActions(headerNode);
    return () => setHeaderActions(null);
  }, [headerNode, setHeaderActions]);

  const handleSend = async (content: AgentInputPart[]) => {
    try {
      // 沙箱由运行时按会话自动 provision，前端不再携带容器选择。
      await send(content, activeSessionId);
      return true;
    } catch {
      return false;
    }
  };

  return (
    <div className={cx("playground-shell", selectedSubagent && "playground-shell-split")}>
      <div className="playground-main">
        <div className="playground-conversation-frame">
          <div className="playground-main-column">
            <MessageScrollPanel
              ariaLabel="对话消息"
              className="playground-canvas-shell"
              contentClassName="playground-canvas"
              loading={historyLoading}
              loadingPrevious={historyPrepending}
              onLoadPrevious={historyHasMore && !historyPrepending ? () => void loadPreviousHistory() : undefined}
              preserveScrollKey={historyVersion}
              resetKey={activeSessionId ?? "new-chat"}
              scrollButtonClassName="chat-scroll-tail-floating"
              watch={[chatState.nodes, chatState.streaming]}
            >
              {(tailRef) => (
                <ChatStream
                  nodes={chatState.nodes}
                  streaming={chatState.streaming}
                  agents={agents}
                  selectedSubagent={selectedSubagent}
                  tailRef={tailRef}
                  onOpenSubagent={setSelectedSubagent}
                />
              )}
            </MessageScrollPanel>
            <div className="playground-composer">
              <Composer
                streaming={chatState.streaming}
                disabled={historyLoading}
                agents={agents}
                activeAgentCode={activeAgentCode}
                agentSwitchDisabled={agentSwitchDisabled}
                canCancelAll={hasRunningSubagents}
                onPickAgent={setActiveAgentCode}
                onSend={handleSend}
                onInterrupt={() => void interrupt()}
                onCancelAll={() => void cancelAll()}
              />
            </div>
          </div>
          <SubagentSidePanel
            nodes={chatState.nodes}
            tabs={subagentTabs}
            agents={agents}
            selection={selectedSubagent}
            onSelect={setSelectedSubagent}
            onClose={closeSubagentPanel}
          />
        </div>
      </div>
      <WorkProjectInfoModal
        open={projectRecordsOpen && Boolean(activeProjectId)}
        projectId={activeProjectId}
        initialTab="assets"
        onClose={() => setProjectRecordsOpen(false)}
      />
      <ConfirmationDecisionModal
        open={approvalModalId !== null}
        mode="approve"
        confirmation={approvalRecord}
        saving={approvalSaving}
        onCancel={() => setApprovalModalId(null)}
        onSubmit={(payload) => decideApproval(true, payload)}
        onReject={() => void decideApproval(false, { mode: "once", note: "" })}
      />
    </div>
  );
}

function SandboxStatusChip({
  sandbox,
  loading,
  preparing,
  className = "",
}: {
  sandbox: SandboxContainer | null;
  loading: boolean;
  preparing: boolean;
  className?: string;
}) {
  if (loading) {
    return (
      <div className={cx("sandbox-selector", className)}>
        <span>沙箱加载中…</span>
      </div>
    );
  }
  if (preparing) {
    return (
      <div className={cx("sandbox-selector", className)}>
        <span>沙箱准备中…</span>
      </div>
    );
  }
  if (!sandbox) {
    return (
      <div className={cx("sandbox-selector", className)}>
        <span>沙箱按需自动创建</span>
      </div>
    );
  }
  return (
    <div className={cx("sandbox-selector", className)} title={`容器 ID：${sandbox.container_hash || "等待创建"}`}>
      <Box size={15} />
      <span>{sandbox.container_name}</span>
      <Tag color={SANDBOX_CONTAINER_STATUS_COLOR[sandbox.status]}>
        {SANDBOX_CONTAINER_STATUS_LABEL[sandbox.status]}
      </Tag>
    </div>
  );
}

function SandboxActionButton({ ariaLabel, disabled, icon, onClick, tooltip }: SandboxActionButtonProps) {
  return (
    <Tooltip content={tooltip}>
      <span className="sandbox-action-tooltip">
        <Button
          aria-label={ariaLabel}
          className="sandbox-action-button"
          disabled={disabled}
          icon={icon}
          theme="borderless"
          type="tertiary"
          onClick={onClick}
        />
      </span>
    </Tooltip>
  );
}

// 文件管理器走宿主机 docker-py 直连（不经容器内控制面），因此只要容器在运行即可用。
function describeFilesUnavailable(container: SandboxContainer | null): string | null {
  if (!container) return "沙箱尚未就绪";
  if (container.status !== SANDBOX_CONTAINER_STATUS.RUNNING) return "沙箱未在运行";
  return null;
}
