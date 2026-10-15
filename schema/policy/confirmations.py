from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from schema.common.responses import PaginatedResponse


class ConfirmationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConfirmationMode(StrEnum):
    """批准后的放行方式。"""

    ONCE = "once"      # 一次性：命中一次即消费
    ALWAYS = "always"  # 完全信任：长期有效，直到撤销


class PolicyConfirmationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    action: str
    category: str
    target: str
    reason: str
    status: ConfirmationStatus
    mode: ConfirmationMode | None
    note: str
    decided_by: str
    decided_at: datetime | None
    consumed_at: datetime | None
    revoked_at: datetime | None


class QueryPolicyConfirmationsResponse(PaginatedResponse[PolicyConfirmationSchema]):
    pass


class DecidePolicyConfirmationRequest(BaseModel):
    # 仅「批准」时使用；拒绝时忽略
    mode: ConfirmationMode = ConfirmationMode.ONCE
    note: str = Field(default="", max_length=512)
