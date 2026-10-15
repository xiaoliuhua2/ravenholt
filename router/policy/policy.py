from fastapi import APIRouter, Depends

from handler.policy.policy import (
    read_policy_actions_handler,
    read_policy_handler,
    set_kill_switch_handler,
    update_policy_actions_handler,
    update_policy_config_handler,
)
from middleware.auth import AuthUser, require_user
from router.common.responses import COMMON_ERROR_RESPONSES, CONFLICT_RESPONSE
from schema.common.responses import CommonResponse
from schema.policy.policy import (
    KillSwitchRequest,
    PolicyApprovalsSnapshotSchema,
    PolicySnapshotSchema,
    UpdatePolicyApprovalsRequest,
    UpdatePolicyConfigRequest,
)


router = APIRouter(prefix="/policy", tags=["policy"])


async def read_policy_route() -> CommonResponse[PolicySnapshotSchema]:
    return await read_policy_handler()


async def update_policy_config_route(
    request: UpdatePolicyConfigRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[PolicySnapshotSchema]:
    return await update_policy_config_handler(request, actor=user.username)


async def read_policy_actions_route() -> CommonResponse[PolicyApprovalsSnapshotSchema]:
    return await read_policy_actions_handler()


async def update_policy_actions_route(
    request: UpdatePolicyApprovalsRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[PolicyApprovalsSnapshotSchema]:
    return await update_policy_actions_handler(request, actor=user.username)


async def set_kill_switch_route(
    request: KillSwitchRequest,
    user: AuthUser = Depends(require_user),
) -> CommonResponse[PolicySnapshotSchema]:
    return await set_kill_switch_handler(request, actor=user.username)


router.add_api_route(
    "",
    read_policy_route,
    methods=["GET"],
    dependencies=[Depends(require_user)],
    response_model=CommonResponse[PolicySnapshotSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "",
    update_policy_config_route,
    methods=["PATCH"],
    response_model=CommonResponse[PolicySnapshotSchema],
    responses={**COMMON_ERROR_RESPONSES, **CONFLICT_RESPONSE},
)

router.add_api_route(
    "/actions",
    read_policy_actions_route,
    methods=["GET"],
    dependencies=[Depends(require_user)],
    response_model=CommonResponse[PolicyApprovalsSnapshotSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/actions",
    update_policy_actions_route,
    methods=["PATCH"],
    response_model=CommonResponse[PolicyApprovalsSnapshotSchema],
    responses={**COMMON_ERROR_RESPONSES, **CONFLICT_RESPONSE},
)

router.add_api_route(
    "/kill-switch",
    set_kill_switch_route,
    methods=["POST"],
    response_model=CommonResponse[PolicySnapshotSchema],
    responses={**COMMON_ERROR_RESPONSES, **CONFLICT_RESPONSE},
)
