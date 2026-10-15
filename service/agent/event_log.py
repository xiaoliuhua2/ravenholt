"""Persistence + pagination for the per-session UI timeline event log.

The timeline log stores the exact wire events the client renders, addressed by
a stable ``item_key`` and ordered by a per-session monotonic ``seq``. History
replay and live streaming therefore share one identity space, so the client can
merge them with an idempotent upsert (no content-based de-duplication).
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import cast, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import get_async_session
from logger import get_logger
from model.agent.event_log import AgentEventLog
from schema.agent.subordinates import AgentSubordinateStatus


logger = get_logger(__name__)

# item_key prefix that marks a top-level user message; used for turn-aligned
# pagination so a page never starts in the middle of an agent turn
USER_MESSAGE_KEY_PREFIX = "user_message:"

# item_key prefix for a subagent task frame, keyed by run id
SUBAGENT_KEY_PREFIX = "sa:"

_INTERRUPTED_SUBAGENT_ERROR = "Subagent task was interrupted by backend restart."


async def load_timeline_head(session_id: str) -> tuple[int, dict[str, int]]:
    """Return (max_seq, {item_key: seq}) so an in-memory counter can resume.

    Loading the full key→seq map lets a recovered/re-pooled session re-emit an
    already-persisted item (e.g. a still-running subagent_task) under its
    original seq instead of allocating a fresh one.
    """
    table = AgentEventLog.__table__
    async with get_async_session() as session:
        rows = (await session.execute(
            select(table.c.item_key, table.c.seq).where(table.c.session_id == session_id)
        )).all()
    item_seq = {row.item_key: int(row.seq) for row in rows}
    max_seq = max(item_seq.values(), default=0)
    return max_seq, item_seq


async def upsert_timeline_events(
    session_id: str,
    rows: list[tuple[str, int, str, datetime]],
) -> None:
    """Upsert timeline rows by (session_id, item_key); seq stays first-seen."""
    if not rows:
        return
    table = AgentEventLog.__table__
    values = [
        {
            "session_id": session_id,
            "item_key": item_key,
            "seq": seq,
            "payload": payload,
            "created_at": created_at,
        }
        for item_key, seq, payload, created_at in rows
    ]
    statement = pg_insert(table).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.session_id, table.c.item_key],
        set_={"payload": statement.excluded.payload, "created_at": statement.excluded.created_at},
    )
    async with get_async_session() as session:
        await session.execute(statement)
        await session.commit()


async def persist_subagent_event_unpooled(session_id: str, event: Any) -> None:
    """Durably upsert a subagent_task timeline row when no pooled session can.

    Used on boot recovery (stale-subagent failure) where the parent session is
    not pooled, so the live event bus would otherwise drop the status change.
    Keeps the existing seq when the row already exists; allocates the next seq
    only for a first-ever emission.
    """
    run_id = getattr(event, "run_id", "")
    if not run_id:
        return
    item_key = f"{SUBAGENT_KEY_PREFIX}{run_id}"
    table = AgentEventLog.__table__
    async with get_async_session() as session:
        existing = (await session.execute(
            select(table.c.seq).where(
                table.c.session_id == session_id,
                table.c.item_key == item_key,
            )
        )).first()
        if existing is not None:
            seq = int(existing.seq)
        else:
            max_seq = (await session.execute(
                select(func.max(table.c.seq)).where(table.c.session_id == session_id)
            )).scalar()
            seq = int(max_seq or 0) + 1
        event.seq = seq
        statement = pg_insert(table).values(
            session_id=session_id,
            item_key=item_key,
            seq=seq,
            payload=event.model_dump_json(),
            created_at=event.created_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.session_id, table.c.item_key],
            set_={"payload": statement.excluded.payload, "created_at": statement.excluded.created_at},
        )
        await session.execute(statement)
        await session.commit()


async def settle_stale_running_subagent_events() -> int:
    """Turn timeline frames that still claim a running subagent into terminal ones.

    Subagent status reaches the console as a projected event: native subordinate
    tasks go through the task registry, and on the strix main line the status is
    polled from an in-process ``AgentCoordinator``. A hard kill (SIGKILL, power
    loss, reboot) therefore freezes the last persisted frame at "running" with
    nothing left alive to emit the terminal status, so the subagent panel would
    show Running forever and contradict the (idle) session state.

    No subagent run can outlive a process restart, so every still-running frame
    observed at boot is stale by definition. Called once during startup, before
    the server accepts requests.
    """
    table = AgentEventLog.__table__
    payload_status = func.jsonb_extract_path_text(cast(table.c.payload, JSONB), "status")
    settled = 0

    async with get_async_session() as session:
        rows = (await session.execute(
            select(table.c.session_id, table.c.item_key, table.c.payload).where(
                table.c.item_key.like(f"{SUBAGENT_KEY_PREFIX}%"),
                payload_status == AgentSubordinateStatus.RUNNING.value,
            )
        )).all()
        for row in rows:
            try:
                payload = json.loads(row.payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            payload["status"] = AgentSubordinateStatus.FAILED.value
            if not payload.get("error_preview"):
                payload["error_preview"] = _INTERRUPTED_SUBAGENT_ERROR
            await session.execute(
                update(table)
                .where(
                    table.c.session_id == row.session_id,
                    table.c.item_key == row.item_key,
                )
                .values(payload=json.dumps(payload, ensure_ascii=False))
            )
            settled += 1
        if settled:
            await session.commit()

    if settled:
        logger.info("settled %d interrupted subagent timeline frame(s) at startup", settled)
    return settled


async def fetch_timeline_page(
    session_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> tuple[list[tuple[int, dict[str, Any]]], bool, int | None]:
    """Fetch one turn-aligned page of timeline rows, ascending by seq.

    Returns ``(items, has_more, next_before_seq)`` where ``items`` is a list of
    ``(seq, payload_dict)``. The page is extended backwards to the start of the
    turn that contains its first row so the UI never paints a half turn.
    """
    limit = max(1, limit)
    table = AgentEventLog.__table__

    async with get_async_session() as session:
        latest_stmt = select(table.c.seq, table.c.payload, table.c.item_key).where(
            table.c.session_id == session_id
        )
        if before_seq is not None:
            latest_stmt = latest_stmt.where(table.c.seq < before_seq)
        latest_stmt = latest_stmt.order_by(table.c.seq.desc()).limit(limit)
        rows = list(reversed((await session.execute(latest_stmt)).all()))
        if not rows:
            return [], False, None

        first_seq = int(rows[0].seq)
        if not str(rows[0].item_key).startswith(USER_MESSAGE_KEY_PREFIX):
            turn_start = (await session.execute(
                select(func.max(table.c.seq)).where(
                    table.c.session_id == session_id,
                    table.c.seq < first_seq,
                    table.c.item_key.like(f"{USER_MESSAGE_KEY_PREFIX}%"),
                )
            )).scalar()
            if turn_start is not None and int(turn_start) < first_seq:
                gap_stmt = (
                    select(table.c.seq, table.c.payload, table.c.item_key)
                    .where(
                        table.c.session_id == session_id,
                        table.c.seq >= int(turn_start),
                        table.c.seq < first_seq,
                    )
                    .order_by(table.c.seq.asc())
                )
                gap_rows = (await session.execute(gap_stmt)).all()
                rows = list(gap_rows) + rows
                first_seq = int(rows[0].seq)

        has_more = bool((await session.execute(
            select(table.c.seq).where(
                table.c.session_id == session_id,
                table.c.seq < first_seq,
            ).limit(1)
        )).first())

    items: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        try:
            payload = json.loads(row.payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            items.append((int(row.seq), payload))

    next_before_seq = first_seq if has_more else None
    return items, has_more, next_before_seq
