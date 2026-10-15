import { Empty, TabPane, Tabs, Tag } from "@douyinfe/semi-ui";
import { Boxes, Bug, Download, FileText, GitBranch, List, Network, Route } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { showApiError } from "../../shared/api/feedback";
import { WORK_PROJECT_ASSET_TYPE } from "../../shared/api/contract";
import type {
  BlackboardNode,
  WorkProjectAsset,
  WorkProjectAttackPathStep,
  WorkProjectFinding,
  WorkProjectGraphEdge,
  WorkProjectGraphSnapshot,
  WorkProjectRecords,
} from "../../shared/api/types";
import { getBlackboardSnapshot } from "../../shared/api/workProjects";
import { cx } from "../../shared/lib/className";
import { formatDateTime } from "../../shared/lib/date";
import {
  WORK_PROJECT_ASSET_ORIGIN_COLOR,
  WORK_PROJECT_ASSET_ORIGIN_LABEL,
  WORK_PROJECT_ASSET_TYPE_LABEL,
  WORK_PROJECT_ATTACK_PATH_STATUS_COLOR,
  WORK_PROJECT_ATTACK_PATH_STATUS_LABEL,
  WORK_PROJECT_FINDING_SEVERITY_COLOR,
  WORK_PROJECT_FINDING_SEVERITY_LABEL,
  WORK_PROJECT_FINDING_STATUS_COLOR,
  WORK_PROJECT_FINDING_STATUS_LABEL,
} from "../../shared/lib/labels";
import {
  BLACKBOARD_NODE_STATUS_COLOR,
  BLACKBOARD_NODE_STATUS_LABEL,
  BLACKBOARD_NODE_TYPE_COLOR,
  BLACKBOARD_NODE_TYPE_LABEL,
} from "../../shared/lib/labels";
import { ProjectGraphCanvas } from "./ProjectGraphCanvas";
import { BlackboardGraphCanvas } from "./BlackboardGraphCanvas";
import { exportFindingReport, reportPreviewText, VulnReportModal } from "./VulnReportModal";
import { filledDetailItems, type DetailItem } from "./workProjectDetails";
import { formatWorkProjectAsset } from "./workProjectView";

export type ProjectRecordTab = "assets" | "findings" | "attack-paths" | "graph";

type WorkProjectRecordTabsProps = {
  records: WorkProjectRecords;
  initialTab?: ProjectRecordTab;
  className?: string;
  projectId?: number;
};

export function WorkProjectRecordTabs({
  records,
  initialTab = "assets",
  className,
  projectId,
}: WorkProjectRecordTabsProps) {
  return (
    <Tabs
      type="line"
      className={cx("project-record-tabs", className)}
      defaultActiveKey={initialTab}
    >
      <TabPane tab={<TabLabel icon={<Boxes size={14} />} text="资产" />} itemKey="assets">
        <AssetList assets={records.assets} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Bug size={14} />} text="发现" />} itemKey="findings">
        <FindingList findings={records.findings} assets={records.assets} projectId={projectId} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Route size={14} />} text="攻击路径" />} itemKey="attack-paths">
        <AttackPathList assets={records.assets} graph={records.graph} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Network size={14} />} text="图" />} itemKey="graph">
        <GraphView assets={records.assets} graph={records.graph} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<GitBranch size={14} />} text="黑板" />} itemKey="blackboard">
        <BlackboardList projectId={projectId} />
      </TabPane>
    </Tabs>
  );
}

export function AssetList({ assets }: { assets: WorkProjectAsset[] }) {
  if (!assets.length) return <RecordEmpty title="暂无资产。" />;
  return (
    <div className="project-record-list">
      {assets.map((asset) => (
        <article key={asset.id} className="project-record-row">
          <header>
            <strong>{formatWorkProjectAsset(asset)}</strong>
            <div>
              <Tag>{WORK_PROJECT_ASSET_TYPE_LABEL[asset.type]}</Tag>
              <Tag color={WORK_PROJECT_ASSET_ORIGIN_COLOR[asset.origin]}>{WORK_PROJECT_ASSET_ORIGIN_LABEL[asset.origin]}</Tag>
            </div>
          </header>
          <RecordDetails items={assetBaseMeta(asset)} />
          <RecordDetails className="project-record-details-extension" items={[
            ["横幅", asset.extra?.banner],
          ]} />
        </article>
      ))}
    </div>
  );
}

export function FindingList({
  findings,
  assets,
  projectId,
}: {
  findings: WorkProjectFinding[];
  assets: WorkProjectAsset[];
  projectId?: number;
}) {
  const assetLabels = useAssetLabels(assets);
  // 点开发现卡片 → 展示按 src-hunt 规范版（7 段）排版的详细漏洞报告。
  const [reportFinding, setReportFinding] = useState<WorkProjectFinding | null>(null);
  const [exportingId, setExportingId] = useState<number | null>(null);
  if (!findings.length) return <RecordEmpty title="暂无发现。" />;

  const handleExport = async (finding: WorkProjectFinding) => {
    setExportingId(finding.id);
    try {
      await exportFindingReport(projectId, finding);
    } catch (error) {
      showApiError(error);
    } finally {
      setExportingId(null);
    }
  };

  return (
    <div className="project-record-list">
      {findings.map((finding) => (
        <article
          key={finding.id}
          className="project-record-row project-record-row-clickable"
          role="button"
          tabIndex={0}
          aria-label={`查看漏洞报告：${finding.title}`}
          onClick={() => setReportFinding(finding)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setReportFinding(finding);
            }
          }}
        >
          <header>
            <strong>{finding.title}</strong>
            <div>
              <Tag color={WORK_PROJECT_FINDING_SEVERITY_COLOR[finding.severity]}>{WORK_PROJECT_FINDING_SEVERITY_LABEL[finding.severity]}</Tag>
              <Tag color={WORK_PROJECT_FINDING_STATUS_COLOR[finding.status]}>{WORK_PROJECT_FINDING_STATUS_LABEL[finding.status]}</Tag>
            </div>
          </header>
          <p className="project-record-row-preview">
            {reportPreviewText(finding.description) || finding.impact || "暂无描述"}
          </p>
          <RecordDetails items={[
            ["资产", finding.asset_id ? assetLabels.get(finding.asset_id) ?? `#${finding.asset_id}` : undefined],
            ["关联边", finding.edge_id ? `#${finding.edge_id}` : undefined],
            ["更新时间", formatDateTime(finding.updated_at)],
          ]} />
          <footer className="project-record-row-foot">
            <button
              type="button"
              className="project-record-row-export"
              onClick={(event) => {
                event.stopPropagation();
                void handleExport(finding);
              }}
              disabled={exportingId === finding.id}
              aria-label={`导出漏洞报告（.md）：${finding.title}`}
            >
              <Download size={13} />
              {exportingId === finding.id ? "导出中…" : "导出 .md"}
            </button>
          </footer>
        </article>
      ))}
      <VulnReportModal
        open={reportFinding !== null}
        finding={reportFinding}
        projectId={projectId}
        onClose={() => setReportFinding(null)}
      />
    </div>
  );
}

export function AttackPathList({ assets, graph }: { assets: WorkProjectAsset[]; graph: WorkProjectGraphSnapshot }) {
  const assetLabels = useAssetLabels(assets);
  const edgesById = useMemo(() => new Map(graph.edges.map((edge) => [edge.id, edge])), [graph.edges]);
  if (!graph.attack_paths.length) return <RecordEmpty title="暂无攻击路径。" />;
  const stepsByPath = groupSteps(graph.attack_path_steps);
  return (
    <div className="project-record-list">
      {graph.attack_paths.map((path) => (
        <article key={path.id} className="project-record-row project-attack-path">
          <header>
            <strong>{path.title}</strong>
            <Tag color={WORK_PROJECT_ATTACK_PATH_STATUS_COLOR[path.status]}>{WORK_PROJECT_ATTACK_PATH_STATUS_LABEL[path.status]}</Tag>
          </header>
          {path.summary ? <p>{path.summary}</p> : null}
          <ol>
            {(stepsByPath.get(path.id) ?? []).map((step) => {
              const edge = edgesById.get(step.edge_id);
              return (
                <li key={step.id}>
                  <strong>{edgeLabel(edge, assetLabels)}</strong>
                  {edge?.label ? <span>{edge.label}</span> : null}
                </li>
              );
            })}
          </ol>
        </article>
      ))}
    </div>
  );
}

export function GraphView({ assets, graph }: { assets: WorkProjectAsset[]; graph: WorkProjectGraphSnapshot }) {
  if (!assets.length) return <RecordEmpty title="暂无可绘制的资产。" />;
  return <ProjectGraphCanvas assets={assets} edges={graph.edges} />;
}

// ── BlackboardList ──

function BlackboardList({ projectId }: { projectId?: number }) {
  const [nodes, setNodes] = useState<BlackboardNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "graph">("graph");

  useEffect(() => {
    if (!projectId) {
      setNodes([]);
      return;
    }
    let canceled = false;
    setLoading(true);
    getBlackboardSnapshot(projectId)
      .then((res) => {
        if (!canceled) {
          setNodes(res.data?.nodes ?? []);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!canceled) {
          showApiError(err);
          setLoading(false);
        }
      });
    return () => { canceled = true; };
  }, [projectId]);

  if (!projectId) return <RecordEmpty title="未选择项目。" />;
  if (loading) return <div className="project-record-list"><div className="loading-hint">加载黑板中…</div></div>;
  if (!nodes.length) return <RecordEmpty title="暂无黑板节点。" />;

  return (
    <>
      <div className="project-record-view-toggle">
        <button
          type="button"
          className={viewMode === "graph" ? "active" : ""}
          onClick={() => setViewMode("graph")}
          aria-label="图视图"
        >
          <GitBranch size={14} /> 图
        </button>
        <button
          type="button"
          className={viewMode === "list" ? "active" : ""}
          onClick={() => setViewMode("list")}
          aria-label="列表视图"
        >
          <List size={14} /> 列表
        </button>
      </div>
      {viewMode === "graph" ? (
        <BlackboardGraphCanvas nodes={nodes} />
      ) : (
        <div className="project-record-list">
          {nodes.map((node) => (
            <article key={node.id} className="project-record-row">
              <header>
                <strong>{node.description}</strong>
                <div>
                  <Tag color={BLACKBOARD_NODE_TYPE_COLOR[node.node_type]}>{BLACKBOARD_NODE_TYPE_LABEL[node.node_type]}</Tag>
                  <Tag color={BLACKBOARD_NODE_STATUS_COLOR[node.status]}>{BLACKBOARD_NODE_STATUS_LABEL[node.status]}</Tag>
                </div>
              </header>
              <RecordDetails items={[
                ["父节点 ID", node.parent_ids !== "[]" ? node.parent_ids : undefined],
                ["创建者", node.creator_agent_code || undefined],
                ["置信度", node.confidence < 1 ? `${Math.round(node.confidence * 100)}%` : undefined],
                ["更新时间", formatDateTime(node.updated_at)],
              ]} />
            </article>
          ))}
        </div>
      )}
    </>
  );
}

function useAssetLabels(assets: WorkProjectAsset[]) {
  return useMemo(() => new Map(assets.map((asset) => [asset.id, formatWorkProjectAsset(asset)])), [assets]);
}

function edgeLabel(edge: WorkProjectGraphEdge | undefined, assetLabels: Map<number, string>): string {
  if (!edge) return "未知边";
  const source = assetLabels.get(edge.source_asset_id) ?? `#${edge.source_asset_id}`;
  const target = assetLabels.get(edge.target_asset_id) ?? `#${edge.target_asset_id}`;
  return `${source} → ${target}`;
}

function RecordDetails({ className, items }: { className?: string; items: DetailItem[] }) {
  const visible = filledDetailItems(items);
  if (!visible.length) return null;
  return (
    <div className={cx("project-record-details", className)}>
      {visible.map(([label, value]) => (
        <span key={label}><strong>{label}</strong>{value}</span>
      ))}
    </div>
  );
}

function assetBaseMeta(asset: WorkProjectAsset): DetailItem[] {
  if (asset.type === WORK_PROJECT_ASSET_TYPE.BINARY) {
    return [["路径", asset.path]];
  }
  return [
    ["主机", asset.host],
    ["端口", asset.port?.toString()],
  ];
}

function RecordEmpty({ title }: { title: string }) {
  return <Empty className="empty-state" image={<FileText size={42} />} title={title} description="" />;
}

function TabLabel({ icon, text }: { icon: ReactNode; text: string }) {
  return <span className="workspace-tab-label">{icon}{text}</span>;
}

function groupSteps(steps: WorkProjectAttackPathStep[]) {
  const map = new Map<number, WorkProjectAttackPathStep[]>();
  for (const step of steps) {
    const items = map.get(step.path_id) ?? [];
    items.push(step);
    map.set(step.path_id, items);
  }
  for (const items of map.values()) items.sort((a, b) => a.sequence - b.sequence);
  return map;
}
