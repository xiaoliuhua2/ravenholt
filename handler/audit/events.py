from schema.audit.events import (
    AuditEventSchema,
    DeleteAuditEventsRequest,
    DeleteAuditEventsResponse,
    PurgeAuditEventsRequest,
    PurgeAuditEventsResponse,
    QueryAuditEventsResponse,
)
from schema.common.responses import CommonResponse
from service.audit.store import delete_audit_events, purge_audit_events, query_audit_events


async def query_audit_events_handler(
    *,
    page: int,
    size: int,
    action: str = "",
    decision: str = "",
    keyword: str = "",
) -> CommonResponse:
    result = await query_audit_events(
        page=page,
        size=size,
        action=action,
        decision=decision,
        keyword=keyword,
    )
    return CommonResponse(
        data=QueryAuditEventsResponse(
            page=result.page,
            size=result.size,
            total=result.total,
            items=[AuditEventSchema.model_validate(item) for item in result.items],
        )
    )


async def delete_audit_events_handler(request: DeleteAuditEventsRequest) -> CommonResponse:
    deleted = await delete_audit_events(request.ids)
    return CommonResponse(
        message=f"已删除 {deleted} 条审计记录",
        data=DeleteAuditEventsResponse(deleted=deleted),
    )


async def purge_audit_events_handler(request: PurgeAuditEventsRequest) -> CommonResponse:
    deleted = await purge_audit_events(
        action=request.action,
        decision=request.decision,
        keyword=request.keyword,
    )
    scope = "当前筛选条件下的" if (request.action.strip() or request.decision.strip() or request.keyword.strip()) else "全部"
    return CommonResponse(
        message=f"已删除{scope} {deleted} 条审计记录",
        data=PurgeAuditEventsResponse(deleted=deleted),
    )
