"""人工确认的挂起 / 唤醒原语（命中审批项 → 挂起 → 用户决策 → 就地继续）。

策略闸口命中「未放行的风险审批项」时，:func:`PendingGateRegistry.open` 先建一条挂起
记录，闸口随即对外推一条「待审批」事件并 :func:`wait` 等待；用户在界面上批准 / 拒绝后，
``service.policy.confirmations.decide_confirmation`` 调 :func:`resolve` 把决策唤醒到
挂起处，于是**本次被拦的动作**（而不是等下一轮）继续执行。

三条不变量（都是会翻车的点）：

- **先建记录、再发事件、最后 await**：否则「卡片刚出现就被点批准」会丢唤醒，
  只能挂到超时。
- **一条确认可挂多个等待者**：``ensure_pending_request`` 对同一 ``(action, target)``
  复用同一条 PENDING 记录，并发同特征命令会共用 id，``resolve`` 必须唤醒全部。
- **单进程单 loop 假设**：HTTP 决策与挂起协程在同一事件循环，故可就地唤醒
  （与 ``core.policy.runtime_state`` 的单例同一前提）。若将来以多 worker 运行，
  需改为 DB 轮询或 LISTEN/NOTIFY。
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from enum import StrEnum


class GateOutcome(StrEnum):
    """挂起的最终状态。``PENDING`` 仅表示尚未决策。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class GateEntry:
    outcome: GateOutcome = GateOutcome.PENDING
    session_id: str = ""
    waiters: list[asyncio.Future[bool]] = field(default_factory=list)

    def wake(self, approved: bool) -> None:
        waiters, self.waiters = self.waiters, []
        for waiter in waiters:
            if not waiter.done():
                waiter.set_result(approved)


class PendingGateRegistry:
    """按 confirmation_id 的进程内挂起注册表。"""

    # 终态记录会留在表里供「晚到的等待者」读到结论（同一确认可能被多条命令共享），
    # 因此需要上限清理；与 concurrency_guard 一样用粗暴但确定的方式收敛。
    _PRUNE_LIMIT = 4096

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[int, GateEntry] = {}

    def open(self, confirmation_id: int, *, session_id: str = "") -> GateEntry:
        """建（或复用）挂起记录；须在对外发事件**之前**调用。"""
        with self._lock:
            if len(self._entries) >= self._PRUNE_LIMIT:
                self._prune_locked()
            entry = self._entries.get(confirmation_id)
            if entry is None:
                entry = GateEntry(session_id=session_id)
                self._entries[confirmation_id] = entry
            elif session_id:
                entry.session_id = session_id
            return entry

    def _prune_locked(self) -> None:
        terminal = [key for key, entry in self._entries.items() if entry.outcome != GateOutcome.PENDING]
        for key in terminal:
            self._entries.pop(key, None)
        if len(self._entries) >= self._PRUNE_LIMIT:  # 仍有大量在途等待：整体清空兜底
            self._entries.clear()

    def resolve(self, confirmation_id: int, approved: bool) -> bool:
        """把决策写入记录并唤醒全部等待者。

        已有终态（超时 / 已被取消）时不再改写：决策仍会落库，成为后续命中的许可，
        但本次挂起已收场。无记录时返回 False（例如挂起已被中断清理）。
        """
        with self._lock:
            entry = self._entries.get(confirmation_id)
            if entry is None or entry.outcome != GateOutcome.PENDING:
                return False
            entry.outcome = GateOutcome.APPROVED if approved else GateOutcome.REJECTED
        entry.wake(approved)
        return True

    def discard(self, confirmation_id: int, outcome: GateOutcome = GateOutcome.CANCELLED) -> None:
        """同步摘除记录并唤醒等待者（取消路径用，不做 DB 写）。"""
        with self._lock:
            entry = self._entries.pop(confirmation_id, None)
            if entry is not None:
                entry.outcome = outcome
        if entry is not None:
            entry.wake(False)

    def discard_session(self, session_id: str) -> int:
        """摘除某会话的全部挂起（供 ``cancel_all`` 等中断路径一并清理）。"""
        if not session_id:
            return 0
        with self._lock:
            keys = [key for key, entry in self._entries.items() if entry.session_id == session_id]
            entries = [self._entries.pop(key) for key in keys]
        for entry in entries:
            entry.outcome = GateOutcome.CANCELLED
            entry.wake(False)
        return len(entries)

    async def wait(self, confirmation_id: int, *, timeout: float | None) -> GateOutcome:
        """等待决策；返回最终状态。

        ``timeout`` 为 ``None`` 或 ``<= 0`` 表示无限等待。等待期间若外部调用
        :meth:`discard`（中断清理），按 ``CANCELLED`` 收场而不悬挂。
        """
        with self._lock:
            entry = self._entries.get(confirmation_id)
            if entry is None:
                return GateOutcome.CANCELLED
            if entry.outcome != GateOutcome.PENDING:
                return entry.outcome
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            entry.waiters.append(future)

        try:
            if timeout is None or timeout <= 0:
                approved = await future
            else:
                approved = await asyncio.wait_for(future, timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            with self._lock:
                entry = self._entries.get(confirmation_id)
                if entry is not None and entry.outcome == GateOutcome.PENDING:
                    entry.outcome = GateOutcome.TIMEOUT
                    entry.wake(False)
            return GateOutcome.TIMEOUT

        with self._lock:
            entry = self._entries.get(confirmation_id)
            if entry is not None and entry.outcome != GateOutcome.PENDING:
                return entry.outcome
        return GateOutcome.APPROVED if approved else GateOutcome.REJECTED


pending_gate = PendingGateRegistry()


__all__ = ["GateEntry", "GateOutcome", "PendingGateRegistry", "pending_gate"]
