from http import HTTPStatus

from core.policy import policy_loaded
from schema.common.responses import CommonResponse
from schema.policy.policy import (
    KillSwitchRequest,
    UpdatePolicyApprovalsRequest,
    UpdatePolicyConfigRequest,
)
from service.policy.actions import current_actions_snapshot, update_action_gates
from service.policy.config import (
    current_policy_snapshot,
    set_kill_switch,
    update_policy_config,
)


def _policy_unavailable() -> CommonResponse | None:
    if policy_loaded():
        return None
    return CommonResponse(
        code=HTTPStatus.SERVICE_UNAVAILABLE.value,
        message="policy not loaded",
    )


async def read_policy_handler() -> CommonResponse:
    """返回当前生效的红线策略完整快照（策略、版本、文件路径）。"""
    unavailable = _policy_unavailable()
    if unavailable is not None:
        return unavailable
    return CommonResponse(data=current_policy_snapshot())


async def update_policy_config_handler(
    request: UpdatePolicyConfigRequest,
    *,
    actor: str = "",
) -> CommonResponse:
    """应用分组配置变更：写回策略文件并即时生效。"""
    unavailable = _policy_unavailable()
    if unavailable is not None:
        return unavailable
    snapshot = await update_policy_config(request, actor=actor)
    return CommonResponse(data=snapshot)


async def read_policy_actions_handler() -> CommonResponse:
    """返回全部风险审批项的放行状态与命中特征（操作台按钮面板回显用）。"""
    unavailable = _policy_unavailable()
    if unavailable is not None:
        return unavailable
    return CommonResponse(data=current_actions_snapshot())


async def update_policy_actions_handler(
    request: UpdatePolicyApprovalsRequest,
    *,
    actor: str = "",
) -> CommonResponse:
    """应用审批项变更（放行 / 命中特征）：写回策略文件并即时生效。"""
    unavailable = _policy_unavailable()
    if unavailable is not None:
        return unavailable
    snapshot = await update_action_gates(request, actor=actor)
    return CommonResponse(data=snapshot)


async def set_kill_switch_handler(
    request: KillSwitchRequest,
    *,
    actor: str = "",
) -> CommonResponse:
    """置位 / 解除急停开关。置位后所有出网动作立即被拒。"""
    unavailable = _policy_unavailable()
    if unavailable is not None:
        return unavailable
    snapshot = await set_kill_switch(request.engaged, actor=actor)
    return CommonResponse(data=snapshot)
