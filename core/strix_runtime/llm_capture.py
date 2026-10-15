"""装配层模型包裹器：捕获每次 LLM 调用的**请求 / 响应原文**并落旁路归档。

为什么在装配层而不是改 strix：ravenholt 把 ``build_configured_model`` 产出的模型**显式**
传给 ``run_strix_session``，因此 strix 自己的 ``get_model`` 包裹链（``RequestLoggingModel`` /
``_TurnGuardModel``）对 ravenholt 会话**不生效** —— 上游那套遥测在本项目里是死代码。
本模块在自己这侧包裹一层，既不修改 vendor 进 ravenholt 的 ``strix`` 包，又能拿到原文。

安全：调用方传入的参数里可能夹带鉴权头（``model_settings.extra_headers`` 可能含
``Authorization`` / ``api-key``）。序列化前统一做递归脱敏，任何疑似密钥的键都被替换为
``***``，确保落盘的原文里没有可用凭据。
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from agents import (
    AgentOutputSchemaBase,
    Handoff,
    Model,
    ModelResponse,
    ModelRetryAdvice,
    ModelRetryAdviceRequest,
    ModelSettings,
    ModelTracing,
    TResponseInputItem,
    Tool,
)
from agents.stream_events import TResponseStreamEvent
from openai.types.responses.response_prompt_param import ResponsePromptParam

from config import get_config
from core.runtime.archive import archive_llm_call
from logger import get_logger


logger = get_logger(__name__)

_SECRET_KEYS = {
    "authorization", "proxy-authorization", "api-key", "api_key", "apikey", "x-api-key",
    "token", "access_token", "refresh_token", "secret", "client_secret",
    "password", "passwd", "cookie", "set-cookie",
}
_SECRET_SUFFIXES = ("_token", "-token", "_secret", "-secret")
_REDACTED = "***"


def _is_secret_key(key: str) -> bool:
    """只有真正承载凭据的键才脱敏。

    不能按子串匹配：``input_tokens`` / ``output_tokens`` / ``total_tokens`` 是模型的
    用量统计，按 ``token`` 子串匹配会把它们误涂成 ``***``，丢掉关键的消耗信息。
    """
    lowered = key.lower().strip()
    return lowered in _SECRET_KEYS or lowered.endswith(_SECRET_SUFFIXES)


def _sanitize(value: Any, *, depth: int = 0) -> Any:
    """递归脱敏：疑似密钥的键一律替换为 ``***``；深度超限时退化为字符串。"""
    if depth > 8:
        return str(value)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            out[name] = _REDACTED if _is_secret_key(name) else _sanitize(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth=depth + 1) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _sanitize(dump(), depth=depth + 1)
        except Exception:  # noqa: BLE001 - 序列化失败退化为字符串，不阻断捕获
            return str(value)
    return str(value)


def _dump(value: Any) -> str:
    try:
        return json.dumps(_sanitize(value), ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return json.dumps({"_unserializable": str(value)}, ensure_ascii=False)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit > 0 and len(text) > limit:
        return text[:limit], True
    return text, False


def _tool_summary(tools: list[Any]) -> list[dict[str, Any]]:
    """只记工具的名字与描述：完整 schema 与输入体重复，体积收益极低。"""
    out: list[dict[str, Any]] = []
    for tool in tools or ():
        entry: dict[str, Any] = {}
        name = getattr(tool, "name", None)
        if isinstance(name, str):
            entry["name"] = name
        description = getattr(tool, "description", None)
        if isinstance(description, str) and description:
            entry["description"] = description
        out.append(entry)
    return out


def _response_summary(response: ModelResponse | None) -> dict[str, Any]:
    if response is None:
        return {}
    summary: dict[str, Any] = {}
    try:
        summary["output"] = _sanitize(response.output)
    except Exception:  # noqa: BLE001
        summary["output"] = str(response)
    usage = getattr(response, "usage", None)
    if usage is not None:
        summary["usage"] = _sanitize(usage)
    return summary


class LlmCaptureModel(Model):
    """包裹内层模型，捕获每次调用的请求 / 响应原文并写入旁路归档。

    仅做「记录」：所有调用原样转发给内层模型，捕获失败静默降级，绝不影响返回值。
    """

    def __init__(
        self,
        inner: Model,
        *,
        session_id: str,
        model_name: str,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._inner = inner
        self._session_id = session_id
        self._model_name = model_name
        self._provider = provider
        self._base_url = base_url

    @property
    def model(self) -> str:
        return self._model_name

    async def close(self) -> None:
        await self._inner.close()

    def get_retry_advice(self, request: ModelRetryAdviceRequest) -> ModelRetryAdvice | None:
        getter = getattr(self._inner, "get_retry_advice", None)
        if callable(getter):
            return getter(request)
        return None

    # ------------------------------------------------------------------ #
    # capture helpers                                                     #
    # ------------------------------------------------------------------ #

    def _request_payload(
        self,
        *,
        streaming: bool,
        system_instructions: str | None,
        input: Any,  # noqa: A002 - SDK 接口固定命名
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> tuple[str, bool]:
        payload = {
            "model": self._model_name,
            "provider": self._provider,
            "streaming": streaming,
            "system_instructions": system_instructions,
            "input": list(input) if isinstance(input, list) else input,
            "tools": _tool_summary(tools),
            "model_settings": {
                "temperature": getattr(model_settings, "temperature", None),
                "top_p": getattr(model_settings, "top_p", None),
                "max_tokens": getattr(model_settings, "max_tokens", None),
                "tool_choice": getattr(model_settings, "tool_choice", None),
                "parallel_tool_calls": getattr(model_settings, "parallel_tool_calls", None),
                "extra_headers": getattr(model_settings, "extra_headers", None),
                "extra_body": getattr(model_settings, "extra_body", None),
            },
            "output_schema": _sanitize(output_schema),
            "handoffs": [getattr(h, "tool_name", str(h)) for h in (handoffs or ())],
            "previous_response_id": previous_response_id,
            "conversation_id": conversation_id,
            "prompt": _sanitize(prompt),
        }
        limit = int(get_config().archive.llm_body_max_chars)
        return _truncate(_dump(payload), limit)

    def _emit(
        self,
        *,
        outcome: str,
        streaming: bool,
        started_mono: float,
        request_text: str,
        request_truncated: bool,
        response_text: str | None = None,
        response_truncated: bool = False,
        usage: Any = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        try:
            from strix.llm.request_log import current_call_context

            context = current_call_context()
            agent_id = context.agent_id
            agent_name = context.agent_name
        except Exception:  # noqa: BLE001
            agent_id = None
            agent_name = None
        record: dict[str, Any] = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "model": self._model_name,
            "streaming": streaming,
            "outcome": outcome,
            "duration_ms": max(0, int((time.monotonic() - started_mono) * 1000)),
            "request_text": request_text,
            "request_truncated": request_truncated,
        }
        if response_text is not None:
            record["response_text"] = response_text
            record["response_truncated"] = response_truncated
        if usage is not None:
            record["usage"] = _sanitize(usage)
        if error_type is not None:
            record["error_type"] = error_type
            record["error_message"] = (error_message or "")[:2000]
        archive_llm_call(self._session_id, record)

    # ------------------------------------------------------------------ #
    # Model interface                                                     #
    # ------------------------------------------------------------------ #

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],  # noqa: A002
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        started = time.monotonic()
        request_text, request_truncated = self._request_payload(
            streaming=False,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        try:
            response = await self._inner.get_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            )
        except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
            self._emit(
                outcome="error",
                streaming=False,
                started_mono=started,
                request_text=request_text,
                request_truncated=request_truncated,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        limit = int(get_config().archive.llm_body_max_chars)
        response_text, response_truncated = _truncate(
            _dump(_response_summary(response)),
            limit,
        )
        self._emit(
            outcome="success",
            streaming=False,
            started_mono=started,
            request_text=request_text,
            request_truncated=request_truncated,
            response_text=response_text,
            response_truncated=response_truncated,
            usage=getattr(response, "usage", None),
        )
        return response

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],  # noqa: A002
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        started = time.monotonic()
        request_text, request_truncated = self._request_payload(
            streaming=True,
            system_instructions=system_instructions,
            input=input,
            model_settings=model_settings,
            tools=tools,
            output_schema=output_schema,
            handoffs=handoffs,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )
        text_parts: list[str] = []
        completed: Any = None
        try:
            async for event in self._inner.stream_response(
                system_instructions,
                input,
                model_settings,
                tools,
                output_schema,
                handoffs,
                tracing,
                previous_response_id=previous_response_id,
                conversation_id=conversation_id,
                prompt=prompt,
            ):
                event_type = str(getattr(event, "type", ""))
                if event_type in ("response.output_text.delta", "response.text.delta"):
                    delta = getattr(event, "delta", None)
                    if isinstance(delta, str):
                        text_parts.append(delta)
                elif event_type == "response.completed":
                    completed = getattr(event, "response", None)
                yield event
        except BaseException as exc:  # noqa: BLE001 - 记录后原样抛出
            self._emit(
                outcome="error",
                streaming=True,
                started_mono=started,
                request_text=request_text,
                request_truncated=request_truncated,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise
        summary: dict[str, Any] = {}
        if completed is not None:
            summary = _response_summary(None)
            summary["output"] = _sanitize(getattr(completed, "output", None))
            summary["usage"] = _sanitize(getattr(completed, "usage", None))
            summary["status"] = _sanitize(getattr(completed, "status", None))
        else:
            summary["output_text"] = "".join(text_parts)
        limit = int(get_config().archive.llm_body_max_chars)
        response_text, response_truncated = _truncate(_dump(summary), limit)
        self._emit(
            outcome="success",
            streaming=True,
            started_mono=started,
            request_text=request_text,
            request_truncated=request_truncated,
            response_text=response_text,
            response_truncated=response_truncated,
            usage=summary.get("usage"),
        )


__all__ = ["LlmCaptureModel"]
