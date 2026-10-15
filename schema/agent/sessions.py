from datetime import datetime
from enum import StrEnum

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from schema.agent.events import AgentContentEventSchema, AgentEventSchema, AgentInputPart, validate_agent_input_content


# canonical agent session type; reused by the model and by the public schema
class SessionType(StrEnum):
    CHAT = "chat"
    PROJECT = "project"


# agent session summary composed from SDK sessions + session metadata
class AgentSessionSummarySchema(BaseModel):
    session_id: str
    session_type: SessionType = SessionType.CHAT
    title: str = ""
    agent_code: str = ""
    owner_id: int = 0
    project_id: int | None = None
    selected_sandbox_container_id: int | None = None
    selected_sandbox_container_generation: int = 0
    is_running: bool = False
    runtime_agent_code: str = ""
    runtime_sandbox_container_id: int | None = None
    runtime_sandbox_container_generation: int = 0
    run_started_at: datetime | None = None
    run_finished_at: datetime | None = None
    run_error: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


# list agent sessions response schema
class ListAgentSessionsResponse(BaseModel):
    items: list[AgentSessionSummarySchema]


# a page of the persisted UI timeline log, ordered ascending by seq
class ListAgentEventsResponse(BaseModel):
    session_id: str
    items: list[AgentContentEventSchema]
    has_more: bool = False
    next_before_seq: int | None = None


class AgentTurnRequest(BaseModel):
    content: list[AgentInputPart] = Field(min_length=1, max_length=8)
    agent_code: str | None = Field(min_length=1, max_length=32)
    sandbox_container_id: int | None = Field(gt=0)

    @field_validator("content", mode="after")
    @classmethod
    def validate_content(cls, value: list[AgentInputPart]) -> list[AgentInputPart]:
        validate_agent_input_content(value)
        return value


class AgentTurnResponse(BaseModel):
    session_id: str
    session: AgentSessionSummarySchema
    events: list[AgentEventSchema]


# Strix 运行时驱动的回合：由 root 在运行时动态派生子代理，故只给一个任务描述。
# 富文本输入（含附件图片）走 content，与 task 至少提供一个。
class StrixTurnRequest(BaseModel):
    # 纯文本任务；与 content 至少提供一个（见下方 model_validator）。
    # 用 None 而非 "" 作为默认：带 default 的字段会被前端生成器当成必填。
    task: str | None = Field(default=None, max_length=20000)
    content: list[AgentInputPart] | None = Field(default=None, min_length=1, max_length=8)
    agent_code: str | None = Field(default=None, min_length=1, max_length=32)

    @field_validator("task", mode="before")
    @classmethod
    def normalize_task(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("content", mode="after")
    @classmethod
    def validate_content(cls, value: list[AgentInputPart] | None) -> list[AgentInputPart] | None:
        if value is not None:
            validate_agent_input_content(value)
        return value

    @model_validator(mode="after")
    def require_task_or_content(self) -> "StrixTurnRequest":
        if not self.task and not self.content:
            raise ValueError("task 与 content 至少提供一个")
        return self


class UpdateAgentSessionTitleRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


# one available agent; surfaced to the @-mention picker in the chat input
class AgentInfoSchema(BaseModel):
    code: str
    name: str
    description: str = ""


# list of agents + the default agent for brand-new sessions
class ListAgentsResponse(BaseModel):
    items: list[AgentInfoSchema]
    default_code: str
