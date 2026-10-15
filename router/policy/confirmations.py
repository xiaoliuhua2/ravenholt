from fastapi import APIRouter, Depends, Query

from handler.policy.confirmations import (
    approve_policy_confirmation_handler,
    delete_policy_confirmation_handler,
    query_policy_confirmations_handler,
    reject_policy_confirmation_handler,
    revoke_policy_confirmation_handler,
)
from middleware.auth import AuthUser, require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.common.responses import CommonResponse
from schema.policy.confirmations import (
    DecidePolicyConfirmationRequest,
    PolicyConfirmationSchema,
    QueryPolicyConfirmationsResponse,
)


NOT_FOUND_RESPONSE = not_found_response("Policy confirmation")
ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/policy/confirmations", tags=["policy"])


async def query_policy_confirmations_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    status: str = Query(default=""),
) -> CommonResponse[QueryPolicyConfirmationsResponse]:
    return await query_policy_confirmations_handler(page=page, size=size, status=status)


async def approve_policy_confirmation_route(
    id: int,
    request: DecidePolicyConfirmationRequest,
    user: AuthUser = Depends(require_admin),
) -> CommonResponse[PolicyConfirmationSchema]:
    return await approve_policy_confirmation_handler(id, request, actor=user.username)


async def reject_policy_confirmation_route(
    id: int,
    request: DecidePolicyConfirmationRequest,
    user: AuthUser = Depends(require_admin),
) -> CommonResponse[PolicyConfirmationSchema]:
    return await reject_policy_confirmation_handler(id, request, actor=user.username)


async def revoke_policy_confirmation_route(
    id: int,
    user: AuthUser = Depends(require_admin),
) -> CommonResponse[PolicyConfirmationSchema]:
    return await revoke_policy_confirmation_handler(id, actor=user.username)


async def delete_policy_confirmation_route(
    id: int,
    _: AuthUser = Depends(require_admin),
) -> CommonResponse:
    return await delete_policy_confirmation_handler(id)


router.add_api_route(
    "",
    query_policy_confirmations_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QueryPolicyConfirmationsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}/approve",
    approve_policy_confirmation_route,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[PolicyConfirmationSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/reject",
    reject_policy_confirmation_route,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[PolicyConfirmationSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/revoke",
    revoke_policy_confirmation_route,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[PolicyConfirmationSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}",
    delete_policy_confirmation_route,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse,
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)
