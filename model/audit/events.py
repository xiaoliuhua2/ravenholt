from datetime import datetime
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class AuditEvent(SQLModel, table=True):
    """红线策略审计：每次出网动作的判定都留痕（Tier-1，不可关闭）。"""

    __tablename__ = "audit_events"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    action: str = Field(default="", index=True)
    category: str = Field(default="")
    target: str = Field(default="", index=True)
    decision: str = Field(default="", index=True)
    code: str = Field(default="", index=True)
    reason: str = Field(default="")
    policy_revision: int = Field(default=0)
    actor: str = Field(default="")
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
