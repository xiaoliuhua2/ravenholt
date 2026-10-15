from http import HTTPStatus

from schema.common.responses import CommonResponse
from schema.policy.confirmations import (
    DecidePolicyConfirmationRequest,
    PolicyConfirmationSchema,
    QueryPolicyConfirmationsResponse,
)
from service.policy.confirmations import (
    decide_confirmation,
    delete_confirmation,
    query_confirmations,
    revoke_confirmation,
)


async def query_policy_confirmations_handler(
    *, page: int, size: int, status: str = ""
) -> CommonResponse:
    result = await query_confirmations(page=page, size=size, status=status)
    return CommonResponse(
        data=QueryPolicyConfirmationsResponse(
            page=result.page,
            size=result.size,
            total=result.total,
            items=[PolicyConfirmationSchema.model_validate(item) for item in result.items],
        )
    )


async def approve_policy_confirmation_handler(
    confirmation_id: int,
    request: DecidePolicyConfirmationRequest,
    *,
    actor: str = "",
) -> CommonResponse:
    result = await decide_confirmation(
        confirmation_id,
        approve=True,
        mode=request.mode,
        note=request.note,
        decided_by=actor,
    )
    if not result.found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=result.message)
    if not result.ok:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=PolicyConfirmationSchema.model_validate(result.confirmation))


async def reject_policy_confirmation_handler(
    confirmation_id: int,
    request: DecidePolicyConfirmationRequest,
    *,
    actor: str = "",
) -> CommonResponse:
    result = await decide_confirmation(
        confirmation_id,
        approve=False,
        note=request.note,
        decided_by=actor,
    )
    if not result.found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=result.message)
    if not result.ok:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=PolicyConfirmationSchema.model_validate(result.confirmation))


async def revoke_policy_confirmation_handler(
    confirmation_id: int,
    *,
    actor: str = "",
) -> CommonResponse:
    result = await revoke_confirmation(confirmation_id, actor=actor)
    if not result.found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=result.message)
    if not result.ok:
        return CommonResponse(code=HTTPStatus.BAD_REQUEST.value, message=result.message)
    return CommonResponse(data=PolicyConfirmationSchema.model_validate(result.confirmation))


async def delete_policy_confirmation_handler(confirmation_id: int) -> CommonResponse:
    result = await delete_confirmation(confirmation_id)
    if not result.found:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message=result.message)
    return CommonResponse(message=result.message)
