"""Self-test for config-reload stream restarts (agent stream discipline).

Offline: no DB / no HTTP / no model calls. Run from the project root:

    .venv/bin/python scripts/verify_stream_restart_selftest.py              # POSIX
    .venv\\Scripts\\python.exe scripts\\verify_stream_restart_selftest.py   # Windows

Saving the instance config rebuilds the agent runtime pool, which tears down
every pooled session's event streams. Two things must hold:

  1. subscribers receive a ``SubscriberClosed`` sentinel carrying the
     application close code (4001) plus a reason — not a bare ``None`` — so the
     frontend can tell "server restarted the stream" apart from a network drop
     and reconnect instead of reporting a misleading connection error;
  2. ``rebuild_agent_instances()`` defers the pool swap while any pooled session
     is still running a turn, and only swaps once they converge — saving the
     config must not abort an in-flight turn mid-tool.

Exit code is non-zero if any expectation fails.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from core.runtime.session import (  # noqa: E402
    SUBSCRIBER_CLOSED_CODE,
    AgentSession,
    SubscriberClosed,
)
from service.system_config import config as config_service  # noqa: E402


class _FakePool:
    """Minimal stand-in exposing only what the rebuild decision reads/writes."""

    def __init__(self, running: bool) -> None:
        self.running = running
        self.stop_calls: list[str] = []

    def has_running_sessions(self) -> bool:
        return self.running

    async def stop(self, *, reason: str = "") -> None:
        self.stop_calls.append(reason)


async def check_close_signal() -> None:
    session = AgentSession("selftest-session")
    queue = await session.subscribe()
    await session.close(reason="instance config updated")

    signal = await asyncio.wait_for(queue.get(), timeout=2)
    assert isinstance(signal, SubscriberClosed), f"expected SubscriberClosed, got {signal!r}"
    assert signal.code == SUBSCRIBER_CLOSED_CODE == 4001, f"unexpected close code {signal.code}"
    assert signal.reason == "instance config updated", f"unexpected reason {signal.reason!r}"
    assert queue.empty(), "expected exactly one close signal"
    print(f"OK  close signal: code={signal.code} reason={signal.reason!r}")


async def check_rebuild_deferral() -> None:
    swaps: list[bool] = []
    original_swap = config_service._swap_agent_pool
    original_get_pool = config_service.get_agent_pool
    original_grace = config_service._DEFERRED_REBUILD_GRACE_SECONDS
    original_poll = config_service._DEFERRED_REBUILD_POLL_SECONDS

    async def fake_swap() -> None:
        swaps.append(True)

    config_service._swap_agent_pool = fake_swap
    config_service._DEFERRED_REBUILD_GRACE_SECONDS = 0.2
    config_service._DEFERRED_REBUILD_POLL_SECONDS = 0.05
    try:
        busy = _FakePool(running=True)
        config_service.get_agent_pool = lambda: busy  # type: ignore[assignment]
        config_service._deferred_rebuild_task = None

        applied = await config_service.rebuild_agent_instances()
        assert applied is False, "a running turn must defer the rebuild"
        assert swaps == [], "the pool must not be swapped while a turn is running"
        pending = config_service._deferred_rebuild_task
        assert pending is not None, "a deferred rebuild must be queued"
        print("OK  running turn: rebuild deferred, pool untouched")

        await config_service.rebuild_agent_instances()
        assert config_service._deferred_rebuild_task is pending, "pending rebuild must be coalesced"
        print("OK  repeated save: pending rebuild coalesced")

        busy.running = False
        await asyncio.wait_for(pending, timeout=5)
        assert swaps == [True], "the deferred rebuild must swap once sessions converge"
        print("OK  after the turn finished: deferred rebuild swapped the pool")

        idle = _FakePool(running=False)
        config_service.get_agent_pool = lambda: idle  # type: ignore[assignment]
        applied = await config_service.rebuild_agent_instances()
        assert applied is True and len(swaps) == 2, "an idle pool must rebuild immediately"
        print("OK  idle pool: rebuild applied immediately")
    finally:
        config_service._swap_agent_pool = original_swap
        config_service.get_agent_pool = original_get_pool
        config_service._DEFERRED_REBUILD_GRACE_SECONDS = original_grace
        config_service._DEFERRED_REBUILD_POLL_SECONDS = original_poll


async def main() -> int:
    await check_close_signal()
    await check_rebuild_deferral()
    print("STREAM_RESTART_SELFTEST_DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
