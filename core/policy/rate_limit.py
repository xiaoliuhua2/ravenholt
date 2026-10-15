"""进程内令牌桶限速器。

契约：``allow(key, limit_per_minute, burst)`` → 是否放行。
每个 key 一个桶，容量 = ``burst``，填充速率 = ``limit_per_minute / 60`` 每秒。
线程安全（服务端有同步线程池会调用到这里）。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


_PRUNE_THRESHOLD = 4096
_PRUNE_AGE_SECONDS = 600.0


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str, limit_per_minute: int, burst: int) -> bool:
        if limit_per_minute <= 0:
            # 非法参数从严：不放行（策略层校验已保证 >= 1，这里只是兜底）
            return False

        capacity = float(max(1, burst))
        rate_per_second = limit_per_minute / 60.0
        now = time.monotonic()

        with self._lock:
            if len(self._buckets) > _PRUNE_THRESHOLD:
                self._prune(now)

            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=capacity, updated_at=now)
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(capacity, bucket.tokens + elapsed * rate_per_second)
                bucket.updated_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    def _prune(self, now: float) -> None:
        """桶数量过多时清掉长期未用的，避免 target 键无限增长。"""
        stale = [k for k, b in self._buckets.items() if now - b.updated_at > _PRUNE_AGE_SECONDS]
        for key in stale:
            self._buckets.pop(key, None)


limiter = TokenBucketLimiter()
