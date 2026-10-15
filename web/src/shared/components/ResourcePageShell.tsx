import { Button, Empty, Input, Select, Spin } from "@douyinfe/semi-ui";
import { Search } from "lucide-react";
import { FormEvent, ReactNode, useState } from "react";

type ResourceMetric = {
  label: string;
  value: ReactNode;
};

type ResourcePageShellProps = {
  searchPlaceholder?: string;
  keyword?: string;
  loading: boolean;
  metrics: ResourceMetric[];
  empty: boolean;
  emptyIcon: ReactNode;
  emptyTitle: string;
  page: number;
  rangeStart: number;
  rangeEnd: number;
  total: number;
  canGoBack: boolean;
  canGoNext: boolean;
  children: ReactNode;
  // 工具栏左侧的附加筛选控件；不传则工具栏只保留搜索框。
  filters?: ReactNode;
  onKeywordChange?: (keyword: string) => void;
  // 不传表示该页面不提供关键词搜索，工具栏不渲染搜索框。
  onSearch?: () => void;
  onPrevious: () => void;
  onNext: () => void;
  // 可选分页增强：不传则分页区维持「上一页 / 下一页」原样。
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
  onJumpToPage?: (page: number) => void;
};

export function ResourcePageShell({
  searchPlaceholder,
  keyword,
  loading,
  metrics,
  empty,
  emptyIcon,
  emptyTitle,
  page,
  rangeStart,
  rangeEnd,
  total,
  canGoBack,
  canGoNext,
  children,
  filters,
  onKeywordChange,
  onSearch,
  onPrevious,
  onNext,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  onJumpToPage,
}: ResourcePageShellProps) {
  const [jumpValue, setJumpValue] = useState("");

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch?.();
  };

  const handleJump = () => {
    const target = Number(jumpValue.trim());
    if (!Number.isFinite(target) || target < 1) {
      setJumpValue("");
      return;
    }
    onJumpToPage?.(target);
    setJumpValue("");
  };

  return (
    <section className="resource-page">
      <MetricStrip metrics={metrics} />

      <div className="table-panel">
        <div className="table-toolbar">
          {filters ? <div className="table-toolbar-filters">{filters}</div> : null}
          {onSearch ? (
            <form className="table-toolbar-search" onSubmit={handleSearch}>
              <Input
                prefix={<Search size={16} />}
                value={keyword ?? ""}
                onChange={(value) => onKeywordChange?.(value)}
                placeholder={searchPlaceholder}
                showClear
              />
              <Button htmlType="submit" theme="solid" type="primary" icon={<Search size={16} />}>
                搜索
              </Button>
            </form>
          ) : null}
        </div>

        <Spin spinning={loading} wrapperClassName="resource-table-spin">
          {empty ? <Empty className="empty-state" image={emptyIcon} title={emptyTitle} description="" /> : children}
        </Spin>

        <div className="pager-row">
          <span>
            第 {page} 页 · 第 {rangeStart}-{rangeEnd} 条 / 共 {total} 条
          </span>
          <div className="pager-controls">
            {pageSizeOptions?.length && onPageSizeChange ? (
              <Select
                className="pager-size-select"
                value={String(pageSize ?? pageSizeOptions[0])}
                optionList={pageSizeOptions.map((count) => ({ label: `${count} 条/页`, value: String(count) }))}
                onChange={(value) => {
                  if (typeof value === "string") onPageSizeChange(Number(value));
                }}
              />
            ) : null}
            {onJumpToPage ? (
              <span className="pager-jump">
                <Input
                  value={jumpValue}
                  onChange={setJumpValue}
                  onEnterPress={handleJump}
                  placeholder="页码"
                  aria-label="跳转到指定页"
                />
                <Button type="tertiary" disabled={loading} onClick={handleJump}>跳转</Button>
              </span>
            ) : null}
            <Button type="tertiary" disabled={!canGoBack || loading} onClick={onPrevious}>上一页</Button>
            <Button type="tertiary" disabled={!canGoNext || loading} onClick={onNext}>下一页</Button>
          </div>
        </div>
      </div>
    </section>
  );
}

export function MetricStrip({ metrics }: { metrics: ResourceMetric[] }) {
  return (
    <div className="metric-strip">
      {metrics.map((metric) => (
        <div className="metric-card" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}
