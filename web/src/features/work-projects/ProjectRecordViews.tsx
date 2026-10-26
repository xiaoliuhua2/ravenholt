import { Button, Empty, Input, TabPane, Tabs, Tag } from "@douyinfe/semi-ui";
import { Boxes, Bug, Download, FileText, GitBranch, List, Network, Route } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { showApiError } from "../../shared/api/feedback";
import { WORK_PROJECT_ASSET_TYPE } from "../../shared/api/contract";
import type {
  BlackboardNode,
  WorkProjectAsset,
  WorkProjectAttackPathStep,
  WorkProjectFinding,
  WorkProjectFindingSeverity,
  WorkProjectGraphEdge,
  WorkProjectGraphSnapshot,
  WorkProjectRecords,
} from "../../shared/api/types";
import { getBlackboardSnapshot, listWorkProjectAssets } from "../../shared/api/workProjects";
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
import { exportFindingReport, VulnReportModal } from "./VulnReportModal";
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
        <AssetList projectId={projectId} total={records.assets_total} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Bug size={14} />} text="发现" />} itemKey="findings">
        <FindingList findings={records.findings} assets={records.assets} projectId={projectId} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Route size={14} />} text="攻击路径" />} itemKey="attack-paths">
        <AttackPathList assets={records.assets} graph={records.graph} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<Network size={14} />} text="图" />} itemKey="graph">
        <GraphView assets={records.assets} graph={records.graph} total={records.assets_total} />
      </TabPane>
      <TabPane tab={<TabLabel icon={<GitBranch size={14} />} text="黑板" />} itemKey="blackboard">
        <BlackboardList projectId={projectId} />
      </TabPane>
    </Tabs>
  );
}

const ASSET_PAGE_SIZE = 100;
// 图布局对节点数是平方级开销，超过这个量级只画前 N 个并提示去资产页看全量。
const GRAPH_ASSET_LIMIT = 600;
// 发现页顶部统计的顺序：从最严重到信息。
const FINDING_SEVERITY_ORDER: WorkProjectFindingSeverity[] = ["critical", "high", "medium", "low", "info"];

export function AssetList({ projectId, total }: { projectId?: number; total: number }) {
  const [items, setItems] = useState<WorkProjectAsset[]>([]);
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(total);
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [loading, setLoading] = useState(false);

  // 快照只带前 N 条；资产页始终按页向服务端取，几千条也不会一次性渲染。
  const fetchPage = useCallback(async (targetPage: number, search: string) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const response = await listWorkProjectAssets(projectId, {
        page: targetPage,
        size: ASSET_PAGE_SIZE,
        keyword: search,
      });
      const data = response.data;
      setItems(data?.items ?? []);
      setTotalCount(data?.total ?? 0);
      setPage(targetPage);
    } catch (error) {
      showApiError(error);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    setAppliedKeyword("");
    setPage(1);
    void fetchPage(1, "");
  }, [fetchPage]);

  const applySearch = () => {
    const search = keyword.trim();
    setAppliedKeyword(search);
    void fetchPage(1, search);
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / ASSET_PAGE_SIZE));
  const pageNumbers = pageWindow(page, totalPages);
  const emptyTitle = appliedKeyword ? "没有匹配的资产。" : "暂无资产。";

  return (
    <div className="project-asset-browser">
      <div className="project-asset-toolbar">
        <Input
          size="small"
          value={keyword}
          placeholder="按标识 / 主机 / 路径搜索"
          showClear
          onChange={setKeyword}
          onEnterPress={applySearch}
        />
        <Button size="small" onClick={applySearch} loading={loading}>搜索</Button>
        <span className="project-asset-count">共 {totalCount} 条</span>
      </div>

      <div className="project-asset-list-area">
        {items.length ? (
          <div className="project-record-list">
            {items.map((asset) => (
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
        ) : (
          <RecordEmpty title={loading ? "加载资产中…" : emptyTitle} />
        )}
      </div>

      {totalCount > 0 ? (
        <nav className="project-asset-pager" aria-label="资产分页">
          <Button
            size="small"
            theme="borderless"
            disabled={page <= 1 || loading}
            onClick={() => void fetchPage(page - 1, appliedKeyword)}
          >
            上一页
          </Button>
          {pageNumbers.map((item, index) => (
            item === "gap" ? (
              <span key={`gap-${index}`} className="project-asset-pager-gap">…</span>
            ) : (
              <button
                key={item}
                type="button"
                className={cx("project-asset-pager-page", item === page && "active")}
                disabled={loading}
                onClick={() => void fetchPage(item, appliedKeyword)}
              >
                {item}
              </button>
            )
          ))}
          <span className="project-asset-pager-total">共 {totalPages} 页</span>
          <Button
            size="small"
            theme="borderless"
            disabled={page >= totalPages || loading}
            onClick={() => void fetchPage(page + 1, appliedKeyword)}
          >
            下一页
          </Button>
        </nav>
      ) : null}
    </div>
  );
}

/** 页码窗口：首尾页 + 当前页附近，其余用省略号（几千条时不会铺出几十个按钮）。 */
function pageWindow(current: number, total: number): Array<number | "gap"> {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set<number>([1, total, current - 1, current, current + 1]);
  const sorted = [...pages].filter((value) => value >= 1 && value <= total).sort((a, b) => a - b);
  const result: Array<number | "gap"> = [];
  sorted.forEach((value, index) => {
    if (index > 0 && value - sorted[index - 1] > 1) result.push("gap");
    result.push(value);
  });
  return result;
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
  const [severity, setSeverity] = useState<WorkProjectFindingSeverity | "all">("all");

  // 顶部按严重度统计；点 chip 就地过滤，计数口径始终是全部发现。
  const severityCounts = useMemo(() => {
    const counts: Partial<Record<WorkProjectFindingSeverity, number>> = {};
    for (const finding of findings) {
      counts[finding.severity] = (counts[finding.severity] ?? 0) + 1;
    }
    return counts;
  }, [findings]);
  const visibleFindings = severity === "all"
    ? findings
    : findings.filter((finding) => finding.severity === severity);

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
    <div className="project-findings-panel">
      <div className="finding-severity-bar" role="group" aria-label="按严重度筛选发现">
        <button
          type="button"
          className={cx("finding-severity-chip", severity === "all" && "active")}
          onClick={() => setSeverity("all")}
        >
          全部 <strong>{findings.length}</strong>
        </button>
        {FINDING_SEVERITY_ORDER.map((item) => {
          const count = severityCounts[item] ?? 0;
          return (
            <button
              key={item}
              type="button"
              data-severity={item}
              className={cx("finding-severity-chip", severity === item && "active")}
              disabled={count === 0}
              onClick={() => setSeverity(item)}
            >
              <i className="finding-severity-dot" aria-hidden="true" />
              {WORK_PROJECT_FINDING_SEVERITY_LABEL[item]} <strong>{count}</strong>
            </button>
          );
        })}
      </div>

      <div className="project-record-list project-findings-list">
        {visibleFindings.map((finding) => (
          <article
            key={finding.id}
            className="project-record-row project-record-row-clickable project-finding-row"
            data-severity={finding.severity}
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
            <header className="project-finding-headline">
              <strong title={finding.title}>{finding.title}</strong>
              <Tag color={WORK_PROJECT_FINDING_SEVERITY_COLOR[finding.severity]}>{WORK_PROJECT_FINDING_SEVERITY_LABEL[finding.severity]}</Tag>
              <Tag color={WORK_PROJECT_FINDING_STATUS_COLOR[finding.status]}>{WORK_PROJECT_FINDING_STATUS_LABEL[finding.status]}</Tag>
              <button
                type="button"
                className="project-record-row-export project-finding-export"
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
            </header>
            <RecordDetails className="project-finding-meta" items={[
              ["资产", finding.asset_id ? assetLabels.get(finding.asset_id) ?? `#${finding.asset_id}` : undefined],
              ["关联边", finding.edge_id ? `#${finding.edge_id}` : undefined],
              ["更新时间", formatDateTime(finding.updated_at)],
            ]} />
          </article>
        ))}
      </div>
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

export function GraphView({
  assets,
  graph,
  total,
}: {
  assets: WorkProjectAsset[];
  graph: WorkProjectGraphSnapshot;
  total: number;
}) {
  if (!assets.length) return <RecordEmpty title="暂无可绘制的资产。" />;
  const shown = assets.slice(0, GRAPH_ASSET_LIMIT);
  return (
    <>
      <ProjectGraphCanvas assets={shown} edges={graph.edges} />
      {shown.length < total ? (
        <p className="project-graph-note">
          图只绘制前 {shown.length} 个资产（项目共 {total} 个）；完整清单见「资产」页。
        </p>
      ) : null}
    </>
  );
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
