import { Button, Checkbox, Modal, Popconfirm, Select, Tag, Toast, Tooltip } from "@douyinfe/semi-ui";
import { Download, FileSearch, ScrollText, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { deleteAuditEvents, purgeAuditEvents, queryAuditEvents } from "../../shared/api/auditEvents";
import { showApiError } from "../../shared/api/feedback";
import type { AuditEvent } from "../../shared/api/types";
import { ResourceIdentity, ResourceText, RowActions } from "../../shared/components/ResourceCells";
import { ResourcePageShell } from "../../shared/components/ResourcePageShell";
import { ResourceTable, type ResourceColumn } from "../../shared/components/ResourceTable";
import { useAdminResourceHeader } from "../../shared/hooks/useAdminResourceHeader";
import { usePagedResourceList } from "../../shared/hooks/usePagedResourceList";
import { formatDateTime } from "../../shared/lib/date";
import {
  AUDIT_ACTION_LABEL,
  AUDIT_CATEGORY_COLOR,
  AUDIT_CATEGORY_LABEL,
  AUDIT_DECISION_COLOR,
  AUDIT_DECISION_LABEL,
  type AuditDecision,
} from "../../shared/lib/labels";

const EXPORT_PAGE_SIZE = 100;
const EXPORT_MAX_ROWS = 2000;
const DEFAULT_PAGE_SIZE = 50;
// 每页条数选项：后端上限 1000。
const PAGE_SIZE_OPTIONS = [20, 50, 100, 200, 500, 1000];
const ACTION_OPTIONS = Object.entries(AUDIT_ACTION_LABEL).map(([value, label]) => ({ label, value }));

export function AuditEventsPage() {
  const [actionFilter, setActionFilter] = useState("");
  const [decisionFilter, setDecisionFilter] = useState<AuditDecision | "">("");
  const [detailEvent, setDetailEvent] = useState<AuditEvent | null>(null);
  const [exporting, setExporting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const query = useCallback(
    (params: { page: number; size: number; keyword: string }) => queryAuditEvents({
      page: params.page,
      size: params.size,
      keyword: params.keyword,
      action: actionFilter,
      decision: decisionFilter,
    }),
    [actionFilter, decisionFilter],
  );

  const {
    items: events, page, pageSize, keyword, activeKeyword, loading, loadItems, total, rangeStart, rangeEnd,
    setKeyword, search, resetPage, changePageSize, jumpToPage, previous, next, canGoBack, canGoNext,
  } = usePagedResourceList<AuditEvent>({ pageSize: DEFAULT_PAGE_SIZE, query });

  // 翻页 / 换筛选后清空勾选，避免跨页误删。
  useEffect(() => {
    setSelectedIds(new Set());
  }, [page, activeKeyword, actionFilter, decisionFilter]);

  const summary = useMemo(
    () => events.reduce(
      (acc, event) => ({
        allow: acc.allow + (event.decision === "allow" ? 1 : 0),
        deny: acc.deny + (event.decision === "deny" ? 1 : 0),
      }),
      { allow: 0, deny: 0 },
    ),
    [events],
  );

  // 一键删除的范围提示：有筛选时说明只删筛选结果，避免误清全表。
  const scopeLabel = actionFilter || decisionFilter || activeKeyword ? "当前筛选条件下的" : "全部";

  const pageIds = useMemo(() => events.map((event) => event.id), [events]);
  const allSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (pageIds.every((id) => next.has(id))) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  }, [pageIds]);

  const removeEvents = useCallback(async (ids: number[]) => {
    if (!ids.length) return;
    setDeleting(true);
    try {
      const response = await deleteAuditEvents(ids);
      Toast.success(response.message || `已删除 ${ids.length} 条审计记录`);
      setSelectedIds((current) => {
        const next = new Set(current);
        ids.forEach((id) => next.delete(id));
        return next;
      });
      await loadItems();
    } catch (error) {
      showApiError(error);
    } finally {
      setDeleting(false);
    }
  }, [loadItems]);

  // 一键清空：按当前筛选条件删除（无筛选 = 全部），由确认框做二次确认。
  const purgeEvents = useCallback(async () => {
    setDeleting(true);
    try {
      const response = await purgeAuditEvents({
        action: actionFilter,
        decision: decisionFilter,
        keyword: activeKeyword,
      });
      Toast.success(response.message || "已清空审计记录");
      setSelectedIds(new Set());
      await loadItems();
    } catch (error) {
      showApiError(error);
    } finally {
      setDeleting(false);
    }
  }, [actionFilter, activeKeyword, decisionFilter, loadItems]);

  // 逐页拉取当前筛选条件下的全部记录，最多 EXPORT_MAX_ROWS 行，避免无界请求。
  const exportCsv = useCallback(async () => {
    setExporting(true);
    try {
      const rows: AuditEvent[] = [];
      let pageNo = 1;
      let matched = 0;
      do {
        const response = await queryAuditEvents({
          page: pageNo,
          size: EXPORT_PAGE_SIZE,
          keyword: activeKeyword,
          action: actionFilter,
          decision: decisionFilter,
        });
        const data = response.data;
        if (!data) break;
        rows.push(...data.items);
        matched = data.total;
        pageNo += 1;
      } while (rows.length < matched && rows.length < EXPORT_MAX_ROWS);

      if (rows.length === 0) {
        Toast.info("当前筛选条件下没有可导出的记录");
        return;
      }
      downloadAuditCsv(rows);
      Toast.success(`已导出 ${rows.length} 条审计记录`);
    } catch (error) {
      showApiError(error);
    } finally {
      setExporting(false);
    }
  }, [actionFilter, activeKeyword, decisionFilter]);

  const headerActions = useMemo(
    () => (
      <Button
        icon={<Download size={16} />}
        type="tertiary"
        loading={exporting}
        aria-label="导出审计日志"
        onClick={() => void exportCsv()}
      >
        导出 CSV
      </Button>
    ),
    [exportCsv, exporting],
  );

  useAdminResourceHeader({
    refreshLabel: "刷新审计日志",
    loading: loading || exporting || deleting,
    onRefresh: loadItems,
    extraActions: headerActions,
  });

  const columns: ResourceColumn<AuditEvent>[] = [
    {
      key: "select", header: (
        <Checkbox
          checked={allSelected}
          indeterminate={selectedIds.size > 0 && !allSelected}
          onChange={toggleSelectAll}
          aria-label="全选本页审计记录"
        />
      ), width: "40px",
      render: (event) => (
        <Checkbox
          checked={selectedIds.has(event.id)}
          onChange={() => toggleSelect(event.id)}
          aria-label={`选择审计记录 ${event.id}`}
        />
      ),
    },
    {
      key: "created", header: "时间", width: "136px",
      render: (event) => formatDateTime(event.created_at),
    },
    {
      key: "action", header: "动作", width: "minmax(132px, 1fr)",
      render: (event) => (
        <ResourceIdentity
          icon={<ScrollText size={16} />}
          title={AUDIT_ACTION_LABEL[event.action] ?? event.action}
          detail={event.action}
        />
      ),
    },
    {
      key: "category", header: "分级", width: "76px",
      render: (event) => (
        <Tag color={AUDIT_CATEGORY_COLOR[event.category] ?? "grey"}>
          {AUDIT_CATEGORY_LABEL[event.category] ?? event.category}
        </Tag>
      ),
    },
    {
      key: "target", header: "目标", width: "minmax(96px, 0.85fr)",
      render: (event) => <ResourceText title={event.target}>{event.target || "-"}</ResourceText>,
    },
    {
      key: "decision", header: "结果", width: "minmax(92px, 0.7fr)",
      render: (event) => (
        <span className="audit-decision-cell">
          <Tag color={AUDIT_DECISION_COLOR[event.decision] ?? "grey"}>
            {AUDIT_DECISION_LABEL[event.decision] ?? event.decision}
          </Tag>
          <code className="audit-code">{event.code || "-"}</code>
        </span>
      ),
    },
    {
      key: "reason", header: "原因", width: "minmax(96px, 1fr)",
      render: (event) => <ResourceText title={event.reason}>{event.reason || "-"}</ResourceText>,
    },
    {
      key: "actions", header: "操作", width: "84px",
      render: (event) => (
        <RowActions>
          <Tooltip content="查看详情">
            <Button icon={<FileSearch size={15} />} theme="borderless" type="tertiary"
              aria-label={`查看审计详情 ${event.id}`}
              onClick={() => setDetailEvent(event)}
            />
          </Tooltip>
          <Popconfirm
            title="删除这条审计记录？"
            content="删除后不可恢复。"
            okText="删除"
            cancelText="取消"
            onConfirm={() => void removeEvents([event.id])}
          >
            <Button icon={<Trash2 size={15} />} theme="borderless" type="danger" title="删除"
              aria-label={`删除审计记录 ${event.id}`}
            />
          </Popconfirm>
        </RowActions>
      ),
    },
  ];

  return (
    <div className="audit-page">
      <ResourcePageShell
        searchPlaceholder="搜索目标、原因或判定码"
        keyword={keyword}
        filters={(
          <>
            <Select
              value={actionFilter}
              optionList={[{ label: "全部动作", value: "" }, ...ACTION_OPTIONS]}
              onChange={(value) => {
                if (typeof value !== "string") return;
                setActionFilter(value);
                resetPage();
              }}
            />
            <Select
              value={decisionFilter}
              optionList={[
                { label: "全部结果", value: "" },
                { label: "放行", value: "allow" },
                { label: "拦截", value: "deny" },
              ]}
              onChange={(value) => {
                if (typeof value !== "string") return;
                setDecisionFilter(value as AuditDecision | "");
                resetPage();
              }}
            />
            {selectedIds.size > 0 ? (
              <Popconfirm
                title={`删除选中的 ${selectedIds.size} 条审计记录？`}
                content="删除后不可恢复。"
                okText="删除"
                cancelText="取消"
                onConfirm={() => void removeEvents([...selectedIds])}
              >
                <Button
                  type="danger"
                  theme="light"
                  icon={<Trash2 size={16} />}
                  loading={deleting}
                  aria-label="删除选中的审计记录"
                >
                  删除选中（{selectedIds.size}）
                </Button>
              </Popconfirm>
            ) : null}
            <Popconfirm
              title={`一键删除${scopeLabel} ${total} 条审计记录？`}
              content="删除后不可恢复，请确认范围无误。"
              okText="全部删除"
              cancelText="取消"
              onConfirm={() => void purgeEvents()}
            >
              <Button
                type="danger"
                theme="solid"
                icon={<Trash2 size={16} />}
                loading={deleting}
                disabled={total === 0}
                aria-label="全部删除审计记录"
              >
                全部删除
              </Button>
            </Popconfirm>
          </>
        )}
        loading={loading}
        metrics={[
          { label: "当前结果", value: total },
          { label: "放行", value: summary.allow },
          { label: "拦截", value: summary.deny },
        ]}
        empty={events.length === 0}
        emptyIcon={<ScrollText size={42} />}
        emptyTitle="暂无审计记录"
        page={page}
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        total={total}
        canGoBack={canGoBack}
        canGoNext={canGoNext}
        pageSize={pageSize}
        pageSizeOptions={PAGE_SIZE_OPTIONS}
        onPageSizeChange={changePageSize}
        onJumpToPage={jumpToPage}
        onKeywordChange={setKeyword}
        onSearch={search}
        onPrevious={previous}
        onNext={next}
      >
        <ResourceTable<AuditEvent>
          ariaLabel="审计日志"
          className="audit-events-table"
          columns={columns}
          rows={events}
          rowKey={(event) => event.id}
        />
      </ResourcePageShell>

      <Modal
        title="审计详情"
        visible={Boolean(detailEvent)}
        footer={null}
        width={620}
        onCancel={() => setDetailEvent(null)}
      >
        {detailEvent ? (
          <div className="audit-detail">
            <AuditDetailRow label="时间" value={formatDateTime(detailEvent.created_at)} />
            <AuditDetailRow label="动作" value={`${AUDIT_ACTION_LABEL[detailEvent.action] ?? detailEvent.action}（${detailEvent.action}）`} />
            <AuditDetailRow label="分级" value={AUDIT_CATEGORY_LABEL[detailEvent.category] ?? detailEvent.category} />
            <AuditDetailRow label="目标" value={detailEvent.target || "-"} />
            <AuditDetailRow label="结果" value={`${AUDIT_DECISION_LABEL[detailEvent.decision] ?? detailEvent.decision} · ${detailEvent.code || "-"}`} />
            <AuditDetailRow label="原因" value={detailEvent.reason || "-"} />
            <AuditDetailRow label="操作者" value={detailEvent.actor || "-"} />
            <AuditDetailRow label="策略版本" value={String(detailEvent.policy_revision)} />
            <pre className="audit-detail-json">{JSON.stringify(detailEvent.detail ?? {}, null, 2)}</pre>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}

function AuditDetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="audit-detail-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function downloadAuditCsv(rows: AuditEvent[]) {
  const header = ["时间", "动作", "分级", "目标", "结果", "判定码", "原因", "操作者", "策略版本"];
  const lines = [header.join(",")];
  rows.forEach((row) => {
    lines.push([
      formatDateTime(row.created_at),
      AUDIT_ACTION_LABEL[row.action] ?? row.action,
      AUDIT_CATEGORY_LABEL[row.category] ?? row.category,
      row.target,
      AUDIT_DECISION_LABEL[row.decision] ?? row.decision,
      row.code,
      row.reason,
      row.actor,
      String(row.policy_revision),
    ].map(csvCell).join(","));
  });

  // 前置 BOM 保证 Excel 正确识别 UTF-8 中文
  const blob = new Blob([`\ufeff${lines.join("\r\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `audit-events-${csvTimestamp()}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: string) {
  const text = value ?? "";
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function csvTimestamp() {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}`;
}
