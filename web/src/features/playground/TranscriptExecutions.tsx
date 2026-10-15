import { Button, Tag } from "@douyinfe/semi-ui";
import { ChevronDown, ChevronRight, GitBranch, PanelRightOpen, Wrench } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { NestedTranscript, SubagentExecutionItem, ToolExecutionItem } from "./chatState";
import { cx } from "../../shared/lib/className";
import { subagentStatusColor, subordinateStatusLabel, type SubagentSelection } from "./subagentView";
import { TranscriptContent } from "./Transcript";
import { emptyAgentTranscript, transcriptHasRunningExecution, transcriptItemCount, type ToolBlock } from "./transcriptView";

export function ToolGroup({
  items,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen,
  header,
}: {
  items: ToolBlock[];
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen: boolean;
  header: (props: PanelHeaderProps) => ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className={cx("transcript-panel transcript-panel-tools", live && "transcript-panel-live")}>
      {header({
        icon: <Wrench size={13} />,
        title: "工具",
        count: items.length,
        open,
        onToggle: () => setOpen((next) => !next),
      })}
      {open ? (
        <div className="tool-list">
          {items.map((block) =>
            block.kind === "tool" ? (
              <ToolExecutionBlock
                key={`${block.kind}:${block.id}`}
                item={block}
                live={live}
                selectedSubagent={allowSubagentOpen ? selectedSubagent : null}
                onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
                allowSubagentOpen={allowSubagentOpen}
              />
            ) : (
              <SubagentExecutionBlock
                key={`${block.kind}:${block.id}`}
                item={block}
                selected={allowSubagentOpen && selectedSubagent === block.agentCode}
                selectedSubagent={allowSubagentOpen ? selectedSubagent : null}
                onOpenSubagent={allowSubagentOpen ? onOpenSubagent : undefined}
              />
            ),
          )}
        </div>
      ) : null}
    </div>
  );
}

type PanelHeaderProps = {
  icon: ReactNode;
  title: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
};

function ToolExecutionBlock({
  item,
  live,
  selectedSubagent,
  onOpenSubagent,
  allowSubagentOpen,
}: {
  item: ToolExecutionItem;
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
  allowSubagentOpen: boolean;
}) {
  const [open, setOpen] = useState(false);
  const detailRef = useRef<HTMLDivElement | null>(null);
  const nestedActive = !!item.nested && transcriptHasRunningExecution(item.nested);
  const status = toolExecutionStatus(item, live);
  const displayName = item.name;

  useEffect(() => {
    if (open) detailRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [open]);

  return (
    <div className={cx("execution-row", `execution-row-${status.tone}`)}>
      <button
        type="button"
        className="execution-row-head"
        aria-expanded={open}
        onClick={() => setOpen((next) => !next)}
      >
        <ExecutionName name={displayName} />
        <Tag size="small" color={status.color}>{status.label}</Tag>
        <span className="execution-row-toggle">{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
      </button>
      {open ? (
        <div ref={detailRef} className="execution-row-detail">
          <JsonExecutionSection label="参数" value={item.arguments} />
          {allowSubagentOpen && (item.nested || item.subagentTask) ? (
            <NestedTranscriptPanel
              nested={item.nested ?? emptyAgentTranscript()}
              task={item.subagentTask}
              live={live && (nestedActive || item.subagentTask?.status === "running")}
              selected={selectedSubagent === item.subagentTask?.agentCode}
              selectedSubagent={selectedSubagent}
              onOpenSubagent={onOpenSubagent}
            />
          ) : null}
          {item.resolved ? (
            <ToolOutputSection output={item.output} tone={item.isError ? "error" : undefined} />
          ) : (
            <ExecutionSection label="输出" body={live ? "执行中…" : "无输出（轮次已中断）"} />
          )}
        </div>
      ) : null}
    </div>
  );
}

function SubagentExecutionBlock({
  item,
  selected,
  selectedSubagent,
  onOpenSubagent,
}: {
  item: SubagentExecutionItem;
  selected: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  const [open, setOpen] = useState(false);
  const nested = item.nested;
  const hasNested = Boolean(nested && transcriptItemCount(nested) > 0);

  return (
    <div className={cx("execution-row execution-row-subagent", `execution-row-subagent-${item.status}`, selected && "execution-row-selected")}>
      <div className="execution-row-head execution-row-head-static">
        <ExecutionName name={item.agentCode || "子智能体"} />
        <SubagentStatusTag status={item.status} />
        {hasNested ? (
          <button
            type="button"
            className="execution-row-toggle-button"
            aria-expanded={open}
            aria-label={open ? "收起子智能体思考链" : "展开子智能体思考链"}
            onClick={() => setOpen((next) => !next)}
          >
            {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        ) : null}
        <OpenSubagentButton agentCode={item.agentCode} onOpenSubagent={onOpenSubagent} />
      </div>
      {open && nested ? (
        <div className="execution-row-detail">
          <NestedTranscriptContent
            nested={nested}
            live={item.status === "running"}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
        </div>
      ) : null}
    </div>
  );
}

function NestedTranscriptPanel({
  nested,
  task,
  live,
  selected,
  selectedSubagent,
  onOpenSubagent,
}: {
  nested: NestedTranscript;
  task?: SubagentExecutionItem;
  live: boolean;
  selected: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  const [open, setOpen] = useState(false);
  const itemCount = transcriptItemCount(nested);
  if (itemCount === 0 && !task) return null;
  const hasNested = itemCount > 0;

  return (
    <div className={cx("nested-panel", live && "nested-panel-live", selected && "nested-panel-selected")}>
      <div className="nested-panel-head">
        <button
          type="button"
          className="nested-panel-toggle"
          aria-expanded={open}
          disabled={!hasNested}
          onClick={() => hasNested && setOpen((next) => !next)}
        >
          <GitBranch size={13} />
          <span className="nested-panel-title">
            子智能体{task?.agentCode ? ` - ${task.agentCode}` : nested.agentName ? ` - ${nested.agentName}` : ""}
          </span>
          {task ? <SubagentStatusTag status={task.status} /> : null}
          <span className="nested-panel-count">{itemCount}</span>
          {hasNested ? (
            <span className="execution-row-toggle">{open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</span>
          ) : null}
        </button>
        <OpenSubagentButton agentCode={task?.agentCode} onOpenSubagent={onOpenSubagent} />
      </div>
      {open ? (
        <div className="nested-panel-body">
          <NestedTranscriptContent
            nested={nested}
            live={live}
            selectedSubagent={selectedSubagent}
            onOpenSubagent={onOpenSubagent}
          />
        </div>
      ) : null}
    </div>
  );
}

function NestedTranscriptContent({
  nested,
  live,
  selectedSubagent,
  onOpenSubagent,
}: {
  nested: NestedTranscript;
  live: boolean;
  selectedSubagent?: SubagentSelection | null;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  return (
    <TranscriptContent
      transcript={nested}
      live={live}
      emptyText="暂无输出"
      allowSubagentOpen
      selectedSubagent={selectedSubagent}
      onOpenSubagent={onOpenSubagent}
    />
  );
}

function ExecutionName({ name }: { name: string }) {
  return <span className="execution-row-name" title={name}>{name}</span>;
}

function OpenSubagentButton({
  agentCode,
  onOpenSubagent,
}: {
  agentCode?: string;
  onOpenSubagent?: (selection: SubagentSelection) => void;
}) {
  if (!agentCode || !onOpenSubagent) return null;
  return (
    <Button
      className="execution-row-expand"
      icon={<PanelRightOpen size={13} />}
      size="small"
      theme="borderless"
      type="tertiary"
      onClick={() => onOpenSubagent(agentCode)}
    >
      打开
    </Button>
  );
}

export function SubagentStatusTag({ status }: { status: SubagentExecutionItem["status"] }) {
  return <Tag size="small" color={subagentStatusColor(status)}>{subordinateStatusLabel(status)}</Tag>;
}

export function ExecutionSection({ label, body, tone }: { label: string; body: string; tone?: "error" }) {
  return (
    <div className={cx("execution-section", tone && `execution-section-${tone}`)}>
      <div className="execution-section-label">{label}</div>
      <pre className="execution-section-body">{body}</pre>
    </div>
  );
}

function JsonExecutionSection({ label, value, tone }: { label: string; value: unknown; tone?: "error" }) {
  const json = useMemo(() => tokenizeJson(stringifyJson(value)), [value]);
  return (
    <div className={cx("execution-section", tone && `execution-section-${tone}`)}>
      <div className="execution-section-label">{label}</div>
      <pre className="execution-section-body execution-json-body">
        <code>
          {json.map((token, index) => (
            token.tone ? (
              <span key={`${index}:${token.text}`} className={`json-token-${token.tone}`}>
                {token.text}
              </span>
            ) : token.text
          ))}
        </code>
      </pre>
    </div>
  );
}

function ToolOutputSection({ output, tone }: { output: string; tone?: "error" }) {
  const parsed = useMemo(() => parseJsonText(output), [output]);
  if (!parsed.ok) {
    return <ExecutionSection label="输出" body={output || "(empty)"} tone={tone} />;
  }
  return <JsonExecutionSection label="输出" value={parsed.value} tone={tone} />;
}

function toolExecutionStatus(
  item: ToolExecutionItem,
  live: boolean,
): { label: string; color: "red" | "green" | "amber"; tone: "error" | "ok" | "running" } {
  if (item.resolved && item.isError) return { label: "失败", color: "red", tone: "error" };
  if (item.subagentTask?.status === "failed" || item.subagentTask?.status === "canceled") {
    return { label: subordinateStatusLabel(item.subagentTask.status), color: "red", tone: "error" };
  }
  if (item.subagentTask?.status === "running") return { label: "运行中", color: "amber", tone: "running" };
  if (!item.resolved) {
    // 轮次已结束却没有返回结果，说明这次调用被中断了——不要一直显示运行中
    return live
      ? { label: "运行中", color: "amber", tone: "running" }
      : { label: "已中断", color: "red", tone: "error" };
  }
  return { label: "完成", color: "green", tone: "ok" };
}

function parseJsonText(output: string): { ok: true; value: unknown } | { ok: false } {
  const text = output.trim();
  if (!text) return { ok: true, value: "" };
  try {
    return { ok: true, value: JSON.parse(text) };
  } catch {
    return { ok: false };
  }
}

function stringifyJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2) ?? JSON.stringify(String(value));
  } catch {
    return JSON.stringify(String(value));
  }
}

type JsonToken = { text: string; tone?: "key" | "string" | "number" | "boolean" | "null" };

const JSON_TOKEN_PATTERN = /"(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\btrue\b|\bfalse\b|\bnull\b/g;

function tokenizeJson(source: string): JsonToken[] {
  const tokens: JsonToken[] = [];
  let cursor = 0;
  for (const match of source.matchAll(JSON_TOKEN_PATTERN)) {
    const text = match[0];
    const index = match.index ?? cursor;
    if (index > cursor) tokens.push({ text: source.slice(cursor, index) });
    tokens.push({ text, tone: jsonTokenTone(source, index, text) });
    cursor = index + text.length;
  }
  if (cursor < source.length) tokens.push({ text: source.slice(cursor) });
  return tokens;
}

function jsonTokenTone(source: string, index: number, text: string): JsonToken["tone"] {
  if (text.startsWith("\"")) {
    return /^\s*:/.test(source.slice(index + text.length)) ? "key" : "string";
  }
  if (text === "true" || text === "false") return "boolean";
  if (text === "null") return "null";
  return "number";
}