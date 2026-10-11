from datetime import datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class Evidence(SQLModel, table=True):
    """A replayable differential evidence pack.

    An ``Evidence`` row is the single source of truth that the independent
    verifier replays: it stores the full request package plus the *baseline*
    and *probe* responses and the four-dimension diff between them. Agent
    narratives / memory / thoughts are deliberately NOT stored here — only
    replayable bytes count as evidence.
    """

    __tablename__ = "evidence"

    id: int | None = Field(default=None, primary_key=True)
    # logical target, e.g. a host or a URL prefix
    target: str = Field(default="", index=True)
    method: str = Field(default="GET")
    url: str = Field(default="")
    # full request package: {"method", "url", "headers", "body"|"json"}
    request_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    baseline_status: int = Field(default=0)
    baseline_body: str = Field(default="", sa_column=Column(Text, nullable=False))
    probe_status: int = Field(default=0)
    probe_body: str = Field(default="", sa_column=Column(Text, nullable=False))
    # four-dimension diff between baseline and probe (see service.evidence.diff)
    diff_json: str = Field(default="{}", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.now)
