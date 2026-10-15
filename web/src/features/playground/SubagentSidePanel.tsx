import { Button } from "@douyinfe/semi-ui";
import { GitBranch, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import type { AgentInfo } from "../../shared/api/types";
import { cx } from "../../shared/lib/className";
import type { ChatNode, SubagentExecutionItem } from "./chatState";
import {
  findSubagentTarget,
  type SubagentSelection,
  type SubagentTab,
  type SubagentTarget,
} from "./subagentView";
import { MessageScrollPanel } from "./MessageScrollPanel";
import { TranscriptContent } from "./Transcript";
import { ExecutionSection, SubagentStatusTag } from "./TranscriptExecutions";

export function SubagentSidePanel({
  nodes,
  tabs,
  agents,
  selection,
  onSelect,
  onClose,
}: {
  nodes: ChatNode[];
  tabs: SubagentTab[];
  agents: AgentInfo[];
  selection: SubagentSelection | null;
  onSelect: (selection: SubagentSelection) => void;
  onClose: () => void;
}) {
  const target = useMemo(
    () => selection ? findSubagentTarget(nodes, selection) : null,
    [nodes, selection],
  );
  const open = Boolean(selection);
  const agentNameByCode = useMemo(
    () => new Map(agents.map((agent) => [agent.code, agent.name])),
    [agents],
  );
  const selectionKey = selection ?? "";
  // 当前选中子智能体最新一次 run：状态行放在固定头部，滚动时始终可见。
  const latestRun = target?.runs[target.runs.length - 1] ?? null;
  const tabsRef = useRef<HTMLDivElement | null>(null);

  // 子智能体多起来时标签条会横向溢出：把竖向滚轮映射成横向滑动，
  // 否则靠后的子智能体既不可见也选不中。到达两端时放行给外层，避免卡住页面滚动。
  useEffect(() => {
    const strip = tabsRef.current;
    if (!strip) return;
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY === 0 || event.deltaX !== 0) return;
      const max = strip.scrollWidth - strip.clientWidth;
      if (max <= 0) return;
      const next = Math.max(0, Math.min(max, strip.scrollLeft + event.deltaY));
      if (next === strip.scrollLeft) return;
      strip.scrollLeft = next;
      event.preventDefault();
    };
    strip.addEventListener("wheel", onWheel, { passive: false });
    return () => strip.removeEventListener("wheel", onWheel);
  }, [tabs.length]);

  return (
    <aside className={cx("subagent-side-panel", open && "subagent-side-panel-open")} aria-hidden={!open}>
      <div className="subagent-side-panel-inner">
        <div className="subagent-side-header">
          <div className="subagent-side-heading">
            <GitBranch size={15} />
            <span>子智能体</span>
          </div>
          {tabs.length > 0 ? (
            <div ref={tabsRef} className="subagent-side-tabs" role="tablist" aria-label="子智能体消息">
              {tabs.map((tab) => {
                const active = selection === tab.agentCode;
                // 标签展示子代理名称（派发时给定的中文名）；取不到时回退预设名 / 泛称，
                // 绝不露出实例 ID。
                const label = tab.agentName || agentNameByCode.get(tab.agentCode) || "子智能体";
                return (
                  <button
                    key={tab.agentCode}
                    type="button"
                    className={cx("subagent-tab", active && "subagent-tab-active")}
                    role="tab"
                    aria-selected={active}
                    onClick={() => onSelect(tab.agentCode)}
                  >
                    <span className="subagent-tab-name" title={label}>
                      {label}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : null}
          <Button icon={<X size={14} />} theme="borderless" type="tertiary" onClick={onClose} aria-label="关闭子智能体面板" />
        </div>
        {open && latestRun ? (
          <div className="subagent-side-status">
            <SubagentStatusTag status={latestRun.task.status} />
            <span>{latestRun.task.runId}</span>
            {latestRun.task.status === "running" && latestRun.task.progress ? (
              <span>{latestRun.task.progress}</span>
            ) : null}
          </div>
        ) : null}
        <MessageScrollPanel
          ariaLabel="子智能体消息"
          className="subagent-side-body-shell"
          contentClassName="subagent-side-body"
          enabled={open}
          resetKey={selectionKey}
          scrollButtonClassName="subagent-scroll-tail-floating"
          watch={[target]}
        >
          {(tailRef) => (
            <>
              {target ? <SubagentTargetView target={target} /> : <div className="transcript-empty">子智能体输出已不可用。</div>}
              <div ref={tailRef} className="chat-tail" />
            </>
          )}
        </MessageScrollPanel>
      </div>
    </aside>
  );
}

function SubagentTargetView({ target }: { target: SubagentTarget }) {
  return (
    <div className="subagent-transcript-view">
      {target.runs.map((run) => (
        <SubagentRunView key={run.task.runId} run={run} />
      ))}
    </div>
  );
}

function SubagentRunView({ run }: { run: SubagentTarget["runs"][number] }) {
  const body = run.transcript ? (
    <TranscriptContent
      transcript={run.transcript}
      live={run.live}
      emptyText="No subagent output yet."
      allowSubagentOpen={false}
    />
  ) : (
    <SubagentFallbackResult task={run.task} />
  );

  return (
    <div className="subagent-task-view">
      {body}
    </div>
  );
}

function SubagentFallbackResult({ task }: { task: SubagentExecutionItem }) {
  const failed = task.status === "failed" || task.status === "canceled";
  const label = task.status === "running" ? "Progress" : failed ? "Error Preview" : "Result Preview";
  const body = task.status === "running"
    ? task.progress || "Running"
    : previewBody(task);

  return <ExecutionSection label={label} body={body} tone={failed ? "error" : undefined} />;
}

function previewBody(task: SubagentExecutionItem): string {
  const body = task.resultPreview || task.errorPreview || "(empty)";
  return task.truncated ? `${body}\n\n[Preview truncated]` : body;
}
