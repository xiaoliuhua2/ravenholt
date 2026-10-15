import { useEffect, useState } from "react";
import { queryPolicyConfirmations } from "../../shared/api/policyConfirmations";

const POLL_INTERVAL_MS = 20000;

/**
 * 轮询待确认许可数量，用于导航栏角标。
 * 角标属于辅助信息，请求失败时静默保留上一次计数，不打断主流程。
 */
export function usePendingConfirmationCount(enabled: boolean) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setCount(0);
      return;
    }

    let cancelled = false;
    const load = async () => {
      try {
        const response = await queryPolicyConfirmations({ page: 1, size: 1, status: "pending" });
        if (!cancelled) setCount(response.data?.total ?? 0);
      } catch {
        // 静默：角标失败不影响使用
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled]);

  return count;
}
