"""整份策略的分组配置与急停开关的读写（改动即时生效并写回文件）。

与 ``service/policy/actions.py`` 共用同一把写入锁；两者都遵循
「读当前策略 → 深拷贝改 → 重新校验 → 写回文件 → 重载 → 失败回滚 → 审计」范式。
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import HTTPException

from core.policy import get_policy, load_policy, policy_path, write_policy
from core.policy.loader import PolicyError
from logger import get_logger
from schema.policy.policy import (
    PolicyConfig,
    PolicySnapshotSchema,
    UpdatePolicyConfigRequest,
)
from service.audit.store import record_audit_event
from service.policy.lock import update_lock


logger = get_logger(__name__)

_SECTION_NAMES = (
    "scope",
    "denylist",
    "dos",
    "rate_limit",
    "redline",
    "report_gate",
)


def current_policy_snapshot() -> PolicySnapshotSchema:
    """当前生效策略的完整快照。"""
    policy = get_policy()
    return PolicySnapshotSchema(
        revision=policy.revision,
        policy_path=str(policy_path()),
        policy=policy,
    )


def _apply_and_persist(current: PolicyConfig, next_policy: PolicyConfig) -> None:
    """写回文件并重载；失败时用变更前的策略回滚。"""
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


async def _record_change(changes: list[str], revision: int, actor: str, action: str) -> None:
    try:
        await record_audit_event(
            action=action,
            category="policy",
            target="",
            decision="allow",
            code="ok",
            reason="；".join(changes),
            policy_revision=revision,
            actor=actor,
            detail={"revision": revision, "changes": changes},
        )
    except Exception:  # noqa: BLE001 - 策略已生效，审计失败仅告警
        logger.exception("策略变更审计写入失败（策略已生效）")


async def update_policy_config(
    request: UpdatePolicyConfigRequest,
    *,
    actor: str = "",
) -> PolicySnapshotSchema:
    """应用分组配置变更：写回 policy.yaml 并即时生效。"""
    async with update_lock:
        current = get_policy()
        if request.revision is not None and request.revision != current.revision:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT.value,
                detail="策略已被其它操作更新，请刷新后重试",
            )

        next_policy = current.model_copy(deep=True)
        changes: list[str] = []
        for name in _SECTION_NAMES:
            patch = getattr(request, name)
            if patch is None:
                continue
            if getattr(next_policy, name) == patch:
                continue
            setattr(next_policy, name, patch.model_copy(deep=True))
            changes.append(name)

        if not changes:
            return current_policy_snapshot()

        next_policy.revision = current.revision + 1
        # 重新整体校验：Tier-1 不可关闭等约束仍会被强制（fail-closed）。
        next_policy = PolicyConfig.model_validate(next_policy.model_dump(mode="json"))
        _apply_and_persist(current, next_policy)
        await _record_change(changes, next_policy.revision, actor, "policy.update")
        return current_policy_snapshot()


async def set_kill_switch(engaged: bool, *, actor: str = "") -> PolicySnapshotSchema:
    """置位 / 解除急停开关；置位后所有出网动作立即被拒。"""
    async with update_lock:
        current = get_policy()
        if current.kill_switch.engaged == engaged:
            return current_policy_snapshot()

        next_policy = current.model_copy(deep=True)
        next_policy.kill_switch.engaged = engaged
        next_policy.revision = current.revision + 1
        next_policy = PolicyConfig.model_validate(next_policy.model_dump(mode="json"))
        _apply_and_persist(current, next_policy)
        await _record_change(
            [f"急停开关：{'置位' if engaged else '解除'}"],
            next_policy.revision,
            actor,
            "policy.kill_switch",
        )
        return current_policy_snapshot()
