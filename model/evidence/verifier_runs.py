from datetime import datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class VerifierRun(SQLModel, table=True):
    """One independent replay of an :class:`Evidence` row.

    ``verdict`` is one of ``reproduced`` | ``refuted`` | ``error``:
    the differential still reproduces, it disappeared (fresh matches
    baseline), or the replay itself failed. The verifier is a deterministic
    component and never consults an LLM to decide a verdict.
    """

    __tablename__ = "verifier_runs"

    id: int | None = Field(default=None, primary_key=True)
    evidence_id: int = Field(foreign_key="evidence.id", index=True, ondelete="CASCADE")
    # reproduced | refuted | error
    verdict: str = Field(default="error", index=True)
    diff_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    note: str = Field(default="", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now)
