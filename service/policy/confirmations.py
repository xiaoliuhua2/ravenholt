"""人工确认请求 / 许可的读写。

许可匹配键是 ``(action, target)`` 精确匹配。命中 ``once`` 许可会立即消费；
``always`` 许可长期有效直到撤销。

用户在界面上批准 / 拒绝后，这里除了落库还要**唤醒挂起中的动作**：
``core.policy.enforcer`` 在命中未放行审批项时会挂起等待决策（见 ``core.policy.pending_gate``），
由 :func:`decide_confirmation` 调 ``pending_gate.resolve`` 把决策送回挂起处，
于是本次被拦的动作继续执行，而不是等下一轮重新发起。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from core.policy.pending_gate import pending_gate
from database import get_async_session
from logger import get_logger
from model.policy.confirmations import PolicyConfirmation
from schema.policy.confirmations import ConfirmationMode, ConfirmationStatus
from service.common.pagination import Page, paginate_statement


logger = get_logger(__name__)


@dataclass(frozen=True)
class ConfirmationDecision:
    found: bool
    ok: bool
    message: str
    confirmation: PolicyConfirmation | None = None


async def find_valid_permit(action: str, target: str) -> PolicyConfirmation | None:
    """找出仍有效的许可（once 未消费 / always 未撤销）。"""
    statement = (
        select(PolicyConfirmation)
        .where(PolicyConfirmation.action == action)
        .where(PolicyConfirmation.target == target)
        .where(PolicyConfirmation.status == ConfirmationStatus.APPROVED)
        .where(PolicyConfirmation.revoked_at.is_(None))
        .order_by(PolicyConfirmation.id.desc())
    )
    async with get_async_session() as session:
        rows = list((await session.exec(statement)).all())

    for row in rows:
        if row.mode == ConfirmationMode.ONCE:
            if row.consumed_at is None:
                return row
            continue
        if row.mode == ConfirmationMode.ALWAYS:
            return row
    return None


async def consume_permit(permit_id: int) -> None:
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, permit_id)
        if row is None:
            return
        row.consumed_at = datetime.now()
        row.updated_at = datetime.now()
        session.add(row)
        await session.commit()


async def ensure_pending_request(action: str, category: str, target: str, reason: str = "") -> PolicyConfirmation:
    """同一 (action, target) 只保留一条待批准记录。"""
    statement = (
        select(PolicyConfirmation)
        .where(PolicyConfirmation.action == action)
        .where(PolicyConfirmation.target == target)
        .where(PolicyConfirmation.status == ConfirmationStatus.PENDING)
        .order_by(PolicyConfirmation.id.desc())
    )
    async with get_async_session() as session:
        existing = (await session.exec(statement)).first()
        if existing is not None:
            return existing

        row = PolicyConfirmation(
            action=action,
            category=category,
            target=target,
            reason=reason,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def resolve_confirmation(action: str, category: str, target: str) -> tuple[bool, int | None]:
    """返回 (是否已获许可, 待批准请求 id)。"""
    permit = await find_valid_permit(action, target)
    if permit is not None:
        if permit.mode == ConfirmationMode.ONCE and permit.id is not None:
            await consume_permit(permit.id)
        return True, None

    pending = await ensure_pending_request(action, category, target)
    return False, pending.id


async def query_confirmations(*, page: int, size: int, status: str = "") -> Page:
    statement = select(PolicyConfirmation).order_by(PolicyConfirmation.id.desc())
    if status.strip():
        statement = statement.where(PolicyConfirmation.status == status.strip())
    return await paginate_statement(statement, page=page, size=size)


async def reject_pending_confirmation(confirmation_id: int, *, note: str = "") -> bool:
    """把仍为 ``pending`` 的记录置为拒绝（超时 / 回合中断的收尾用）。

    已是终态（已批准 / 已拒绝）时不动它：用户可能刚好在这之前做了决定。
    """
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, confirmation_id)
        if row is None or row.status != ConfirmationStatus.PENDING:
            return False
        now = datetime.now()
        row.status = ConfirmationStatus.REJECTED
        row.note = (f"{row.note} | {note}".strip(" |")) if note else row.note
        row.decided_at = now
        row.updated_at = now
        session.add(row)
        await session.commit()
        return True


async def consume_once_permit(confirmation_id: int) -> bool:
    """本次动作正是用掉这次批准：``once`` 许可立即写 ``consumed_at``。

    ``always`` 许可不动（长期信任沿用原语义）。
    """
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, confirmation_id)
        if row is None or row.status != ConfirmationStatus.APPROVED:
            return False
        if row.mode != ConfirmationMode.ONCE or row.consumed_at is not None:
            return False
        now = datetime.now()
        row.consumed_at = now
        row.updated_at = now
        session.add(row)
        await session.commit()
        return True


async def settle_stale_pending_confirmations() -> int:
    """启动时把残留的 ``pending`` 记录置为拒绝。

    它们对应的挂起协程已随上次进程退出而消失，不可能再被唤醒；留着只会让
    「策略审批」页显示一堆永远等不到的待批准项，也会被后续请求复用。
    """
    async with get_async_session() as session:
        rows = list((await session.exec(
            select(PolicyConfirmation).where(
                PolicyConfirmation.status == ConfirmationStatus.PENDING
            )
        )).all())
        if not rows:
            return 0
        now = datetime.now()
        for row in rows:
            row.status = ConfirmationStatus.REJECTED
            row.note = (f"{row.note} | Settled after backend restart.".strip(" |"))
            row.decided_at = now
            row.updated_at = now
            session.add(row)
        await session.commit()
        logger.info("启动清理：%s 条残留待批准记录已置为拒绝", len(rows))
        return len(rows)


async def decide_confirmation(
    confirmation_id: int,
    *,
    approve: bool,
    mode: str = "once",
    note: str = "",
    decided_by: str = "",
) -> ConfirmationDecision:
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, confirmation_id)
        if row is None:
            return ConfirmationDecision(False, False, "confirmation not found")
        if row.status != ConfirmationStatus.PENDING:
            return ConfirmationDecision(
                True, False, "only pending confirmations can be decided", row
            )

        now = datetime.now()
        row.status = ConfirmationStatus.APPROVED if approve else ConfirmationStatus.REJECTED
        row.mode = ConfirmationMode(mode) if approve else None
        row.note = note
        row.decided_by = decided_by
        row.decided_at = now
        row.updated_at = now
        session.add(row)
        await session.commit()
        await session.refresh(row)
        # 唤醒挂起中的动作（若有）：仅改动内存中的 future，不碰 DB，因此可留在会话内。
        pending_gate.resolve(confirmation_id, approve)
        return ConfirmationDecision(True, True, "confirmation decided", row)


async def revoke_confirmation(confirmation_id: int, *, actor: str = "") -> ConfirmationDecision:
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, confirmation_id)
        if row is None:
            return ConfirmationDecision(False, False, "confirmation not found")
        if row.status != ConfirmationStatus.APPROVED:
            return ConfirmationDecision(True, False, "only approved permits can be revoked", row)

        now = datetime.now()
        row.revoked_at = now
        if actor:
            row.note = (f"{row.note} | revoked by {actor}").strip(" |")
        row.updated_at = now
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return ConfirmationDecision(True, True, "permit revoked", row)


async def delete_confirmation(confirmation_id: int) -> ConfirmationDecision:
    """删除一条审批记录。

    只清掉这条待办 / 许可记录本身；它在审计日志里的决策痕迹不受影响（审计日志是另一条链路）。
    """
    async with get_async_session() as session:
        row = await session.get(PolicyConfirmation, confirmation_id)
        if row is None:
            return ConfirmationDecision(False, False, "confirmation not found")
        await session.delete(row)
        await session.commit()
        return ConfirmationDecision(True, True, "confirmation deleted")
