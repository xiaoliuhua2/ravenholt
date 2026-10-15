"""审计事件读写。

写入侧**不吞异常**：调用方（``core.policy.enforcer``）依赖它抛错来执行 fail-closed
—— 审计写不进去时，放行路径会被改判为拒绝。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, or_
from sqlmodel import select

from database import get_async_session
from model.audit.events import AuditEvent
from service.common.pagination import Page, paginate_statement


async def record_audit_event(
    *,
    action: str,
    category: str,
    target: str,
    decision: str,
    code: str,
    reason: str,
    policy_revision: int,
    actor: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    event = AuditEvent(
        action=action,
        category=category,
        target=target,
        decision=decision,
        code=code,
        reason=reason,
        policy_revision=policy_revision,
        actor=actor,
        detail=detail or {},
    )
    async with get_async_session() as session:
        session.add(event)
        await session.commit()


def _audit_filters(action: str, decision: str, keyword: str) -> list:
    """筛选条件（动作 / 判定 / 关键词），查询与批量删除共用同一套语义。"""
    conditions: list = []
    if action.strip():
        conditions.append(AuditEvent.action == action.strip())
    if decision.strip():
        conditions.append(AuditEvent.decision == decision.strip())
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(
                AuditEvent.target.ilike(like),
                AuditEvent.reason.ilike(like),
                AuditEvent.code.ilike(like),
            )
        )
    return conditions


async def query_audit_events(
    *,
    page: int,
    size: int,
    action: str = "",
    decision: str = "",
    keyword: str = "",
) -> Page:
    """按时间倒序分页查询审计事件，可按动作/判定过滤、按关键词模糊匹配。"""
    statement = select(AuditEvent).order_by(AuditEvent.id.desc())
    conditions = _audit_filters(action, decision, keyword)
    if conditions:
        statement = statement.where(*conditions)
    return await paginate_statement(statement, page=page, size=size)


async def purge_audit_events(*, action: str = "", decision: str = "", keyword: str = "") -> int:
    """按筛选条件删除审计事件，返回删除条数；三个条件都为空即清空全部。

    与 ``delete_audit_events`` 的区别：后者只删显式 id，这里按条件批量删。
    调用方（管理端页面）负责二次确认。
    """
    async with get_async_session() as session:
        statement = delete(AuditEvent)
        conditions = _audit_filters(action, decision, keyword)
        if conditions:
            statement = statement.where(*conditions)
        result = await session.execute(statement)
        await session.commit()
    return int(result.rowcount or 0)


async def delete_audit_events(ids: Sequence[int]) -> int:
    """按 id 批量删除审计事件，返回实际删除条数。

    只删显式给出的 id：调用方（管理端页面）负责二次确认，这里不做条件式全清，
    避免误删审计链。
    """
    unique_ids = sorted({int(value) for value in ids if int(value) > 0})
    if not unique_ids:
        return 0
    async with get_async_session() as session:
        result = await session.execute(delete(AuditEvent).where(AuditEvent.id.in_(unique_ids)))
        await session.commit()
    return int(result.rowcount or 0)
