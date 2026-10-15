from fastapi import APIRouter, Depends, Query

from handler.audit.events import (
    delete_audit_events_handler,
    purge_audit_events_handler,
    query_audit_events_handler,
)
from middleware.auth import require_admin
from router.common.responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES
from schema.audit.events import (
    DeleteAuditEventsRequest,
    DeleteAuditEventsResponse,
    PurgeAuditEventsRequest,
    PurgeAuditEventsResponse,
    QueryAuditEventsResponse,
)
from schema.common.responses import CommonResponse


ADMIN_ONLY = [Depends(require_admin)]

router = APIRouter(prefix="/audit-events", tags=["audit-events"])


async def query_audit_events_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=1000),
    action: str = Query(default=""),
    decision: str = Query(default=""),
    keyword: str = Query(default=""),
) -> CommonResponse[QueryAuditEventsResponse]:
    return await query_audit_events_handler(
        page=page,
        size=size,
        action=action,
        decision=decision,
        keyword=keyword,
    )


async def delete_audit_events_route(
    request: DeleteAuditEventsRequest,
) -> CommonResponse[DeleteAuditEventsResponse]:
    return await delete_audit_events_handler(request)


async def purge_audit_events_route(
    request: PurgeAuditEventsRequest,
) -> CommonResponse[PurgeAuditEventsResponse]:
    return await purge_audit_events_handler(request)


router.add_api_route(
    "",
    query_audit_events_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QueryAuditEventsResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/delete",
    delete_audit_events_route,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteAuditEventsResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)

router.add_api_route(
    "/purge",
    purge_audit_events_route,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[PurgeAuditEventsResponse],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE},
)
