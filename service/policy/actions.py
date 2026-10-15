"""风险审批项（``src-hunt`` §2）的读写与运行时生效。

面板按条目改：``allow`` 折叠为「已放行 / 需人工审批」，``signals`` 是该项的
命令文本命中特征（可自定义）。改动写回 ``policy.yaml`` 并即时生效。
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import HTTPException

from core.policy import get_policy, load_policy, write_policy
from core.policy.loader import PolicyError
from logger import get_logger
from schema.policy.policy import (
    ApprovalGateSchema,
    ApprovalItem,
    PolicyApprovalsSnapshotSchema,
    PolicyConfig,
    UpdatePolicyApprovalsRequest,
)
from service.audit.store import record_audit_event
from service.policy.lock import update_lock


logger = get_logger(__name__)

# 「读-改-写文件 + 重载」必须串行；与其它策略写接口共用同一把锁。
_actions_lock = update_lock


def _gate_of(item: ApprovalItem) -> ApprovalGateSchema:
    return ApprovalGateSchema(
        key=item.key,
        label=item.label,
        description=item.description,
        allow=item.allow,
        signals=list(item.signals),
    )


def current_actions_snapshot() -> PolicyApprovalsSnapshotSchema:
    """当前全部审批项的状态（供操作台按钮面板回显）。"""
    policy = get_policy()
    return PolicyApprovalsSnapshotSchema(
        revision=policy.revision,
        approvals=[_gate_of(item) for item in policy.approvals],
    )


async def update_action_gates(
    request: UpdatePolicyApprovalsRequest,
    *,
    actor: str = "",
) -> PolicyApprovalsSnapshotSchema:
    """应用审批项变更：写回 policy.yaml 并即时生效（失败回滚）。"""
    async with _actions_lock:
        current = get_policy()
        if request.revision is not None and request.revision != current.revision:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT.value,
                detail="策略已被其它会话更新，请重新打开面板后再试",
            )

        next_policy = current.model_copy(deep=True)
        by_key = {item.key: item for item in next_policy.approvals}
        changes: list[str] = []
        for patch in request.approvals:
            item = by_key.get(patch.key)
            if item is None:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST.value,
                    detail=f"未定义的审批项：{patch.key}",
                )
            if patch.allow is not None and item.allow != patch.allow:
                item.allow = patch.allow
                changes.append(f"{item.label}：{'放行' if patch.allow else '需审批'}")
            if patch.signals is not None and item.signals != list(patch.signals):
                item.signals = list(patch.signals)
                changes.append(f"{item.label}：命中特征已更新")

        if not changes:
            return current_actions_snapshot()

        next_policy.revision = current.revision + 1
        # 重新整体校验：Tier-1 不可关闭、审批项 key 唯一等约束在这里仍会被强制（fail-closed）。
        next_policy = PolicyConfig.model_validate(next_policy.model_dump(mode="json"))

        try:
            write_policy(next_policy)
            load_policy()
        except (OSError, PolicyError) as exc:
            logger.exception("策略写回失败，尝试回滚")
            try:
                write_policy(current)
                load_policy()
            except Exception:  # noqa: BLE001 - 回滚失败只记录，原始错误优先
                logger.exception("策略回滚失败，磁盘可能停在中间态")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                detail=f"策略写入失败，未生效：{exc}",
            ) from exc

        try:
            await record_audit_event(
                action="policy.update",
                category="policy",
                target="",
                decision="allow",
                code="ok",
                reason="；".join(changes),
                policy_revision=next_policy.revision,
                actor=actor,
                detail={"revision": next_policy.revision, "changes": changes},
            )
        except Exception:  # noqa: BLE001 - 策略已生效，审计失败仅告警
            logger.exception("策略变更审计写入失败（策略已生效）")

        return current_actions_snapshot()
