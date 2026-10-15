import { useCallback, useEffect, useRef, useState } from "react";
import { showApiError } from "../api/feedback";

type QueryParams = {
  page: number;
  size: number;
  keyword: string;
};

type QueryResponse<Item> = {
  data?: {
    items: Item[];
    total: number;
  } | null;
};

type UsePagedResourceListOptions<Item> = {
  pageSize?: number;
  query: (params: QueryParams) => Promise<QueryResponse<Item>>;
};

const DEFAULT_PAGE_SIZE = 10;

export function usePagedResourceList<Item>({ pageSize = DEFAULT_PAGE_SIZE, query }: UsePagedResourceListOptions<Item>) {
  const [items, setItems] = useState<Item[]>([]);
  const [page, setPage] = useState(1);
  // 每页条数可被调用方（下拉选择）改；默认沿用入参。
  const [size, setSize] = useState(pageSize);
  const [keyword, setKeyword] = useState("");
  const [activeKeyword, setActiveKeyword] = useState("");
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const requestIdRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => () => {
    mountedRef.current = false;
    requestIdRef.current += 1;
  }, []);

  const loadItems = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    try {
      const response = await query({ page, size, keyword: activeKeyword });
      if (!mountedRef.current || requestIdRef.current !== requestId) return;
      const nextItems = response.data?.items || [];
      if (nextItems.length === 0 && page > 1) {
        setPage((current) => Math.max(1, current - 1));
        return;
      }
      setItems(nextItems);
      setTotal(response.data?.total ?? 0);
    } catch (error) {
      if (mountedRef.current && requestIdRef.current === requestId) {
        showApiError(error);
      }
    } finally {
      if (mountedRef.current && requestIdRef.current === requestId) {
        setLoading(false);
      }
    }
  }, [activeKeyword, page, query, size]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const search = useCallback(() => {
    setPage(1);
    setActiveKeyword(keyword.trim());
  }, [keyword]);

  const previous = useCallback(() => {
    setPage((current) => Math.max(1, current - 1));
  }, []);

  const next = useCallback(() => {
    setPage((current) => current + 1);
  }, []);

  // 筛选条件变化时由调用方主动归位到第 1 页，避免停在越界页码上。
  const resetPage = useCallback(() => {
    setPage(1);
  }, []);

  // 改每页条数后回到第 1 页，避免停在越界页码上。
  const changePageSize = useCallback((nextSize: number) => {
    if (!Number.isFinite(nextSize) || nextSize < 1) return;
    setSize(Math.floor(nextSize));
    setPage(1);
  }, []);

  // 跳到指定页（页码越界时夹到 [1, 总页数]）。
  const jumpToPage = useCallback(
    (target: number) => {
      if (!Number.isFinite(target)) return;
      const pageCount = Math.max(1, Math.ceil(total / size));
      setPage(Math.min(Math.max(1, Math.floor(target)), pageCount));
    },
    [size, total],
  );

  return {
    items,
    page,
    pageSize: size,
    pageCount: Math.max(1, Math.ceil(total / size)),
    keyword,
    activeKeyword,
    total,
    rangeStart: total === 0 ? 0 : (page - 1) * size + 1,
    rangeEnd: Math.min(page * size, total),
    loading,
    loadItems,
    setKeyword,
    search,
    resetPage,
    changePageSize,
    jumpToPage,
    previous,
    next,
    canGoBack: page > 1,
    canGoNext: page * size < total,
  };
}
