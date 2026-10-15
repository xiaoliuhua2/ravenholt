from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schema.common.responses import PaginatedResponse


class AuditEventSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    action: str
    category: str
    target: str
    decision: str
    code: str
    reason: str
    policy_revision: int
    actor: str
    detail: dict[str, Any]


class QueryAuditEventsResponse(PaginatedResponse[AuditEventSchema]):
    pass


class DeleteAuditEventsRequest(BaseModel):
    """按 id 批量删除审计事件（单条删除即只传一个 id）。"""

    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(min_length=1, max_length=1000, description="要删除的审计事件 id 列表。")


class DeleteAuditEventsResponse(BaseModel):
    deleted: int


class PurgeAuditEventsRequest(BaseModel):
    """按筛选条件批量删除审计事件；三个条件都为空即清空全部。

    审计链属敏感数据：调用方（管理端页面）必须先做二次确认。
    """

    model_config = ConfigDict(extra="forbid")

    action: str = ""
    decision: str = ""
    keyword: str = ""


class PurgeAuditEventsResponse(BaseModel):
    deleted: int
