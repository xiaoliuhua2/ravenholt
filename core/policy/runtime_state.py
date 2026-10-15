"""策略运行期状态：并发租约、总请求量计数、拒绝滑动窗口。

这些是「定义了但原先没生效」的策略字段的运行支撑：
- 并发上限 → 按目标（或全局）的信号量，由 ``policy_guard`` 包裹真实动作来持有。
- 总请求量 → 进程内计数器；策略 revision 变化或进程重启即归零（面板文案需说明）。
- 自动急停 → 只统计越界类拒绝（scope / denylist / dos）的滑动窗口次数。
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque


_PRUNE_LIMIT = 4096


class ConcurrencyGuard:
    """按 key 的并发信号量；limit 变化时重建（在途计数会随之重置）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[int, asyncio.Semaphore]] = {}

    def semaphore(self, key: str, limit: int) -> asyncio.Semaphore:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] == limit:
                return entry[1]
            if entry is None and len(self._entries) >= _PRUNE_LIMIT:
                self._entries.clear()
            semaphore = asyncio.Semaphore(max(1, limit))
            self._entries[key] = (limit, semaphore)
            return semaphore


class RequestCounter:
    """进程内总请求量计数；``limit <= 0`` 表示不限。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0
        self._revision = 0

    def check_and_increment(self, limit: int, revision: int) -> bool:
        with self._lock:
            if revision != self._revision:
                self._count = 0
                self._revision = revision
            if limit > 0 and self._count >= limit:
                return False
            self._count += 1
            return True

    def reset(self) -> None:
        with self._lock:
            self._count = 0


class DenialWindow:
    """滑动窗口内的拒绝次数。"""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._lock = threading.Lock()
        self._events: deque[float] = deque()

    def record(self) -> int:
        now = time.monotonic()
        with self._lock:
            self._events.append(now)
            while self._events and now - self._events[0] > self._window:
                self._events.popleft()
            return len(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


concurrency_guard = ConcurrencyGuard()
request_counter = RequestCounter()
denial_window = DenialWindow()
