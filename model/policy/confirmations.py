from datetime import datetime

from sqlmodel import Field, SQLModel

from schema.policy.confirmations import ConfirmationMode, ConfirmationStatus


class PolicyConfirmation(SQLModel, table=True):
    """红线的「需人工确认」请求与许可。

    - 动作首次被要求确认时落一条 ``status=pending`` 的记录（同一 action+target 复用同一条）。
    - 管理员批准时选定 ``mode``：
        * ``once``   ：命中一次后写 ``consumed_at``，之后需重新批准；
        * ``always`` ：长期信任，直到写 ``revoked_at``。
    """

    __tablename__ = "policy_confirmations"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(default_factory=datetime.now)
    action: str = Field(default="", index=True)
    category: str = Field(default="")
    target: str = Field(default="", index=True)
    reason: str = Field(default="")
    status: ConfirmationStatus = Field(default=ConfirmationStatus.PENDING, index=True)
    mode: ConfirmationMode | None = Field(default=None)
    note: str = Field(default="")
    decided_by: str = Field(default="")
    decided_at: datetime | None = Field(default=None)
    consumed_at: datetime | None = Field(default=None)
    revoked_at: datetime | None = Field(default=None)
