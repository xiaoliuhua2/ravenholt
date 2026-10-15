"""Self-test for persisted thinking (reasoning) AND assistant text timeline frames.

Offline: no DB / no HTTP / no model calls. Run from the project root:

    .venv/bin/python scripts/verify_thinking_timeline_selftest.py              # POSIX
    .venv\\Scripts\\python.exe scripts\\verify_thinking_timeline_selftest.py   # Windows

Why this exists: streaming reasoning reaches the console as ``thinking_delta`` and
streaming prose as ``text_delta``, but ``core/runtime/timeline.py`` deliberately
never persists either delta — only the terminal frames are durable. On the
chat-completions path (DeepSeek and most OpenAI-compatible vendors) the SDK emits
``reasoning_summary_part.done`` (no ``reasoning_summary_text.done``) and
``content_part.done`` (no ``response.output_text.done``). Without handling those,
no ``thinking_complete``/``text_complete`` is ever produced and both the thinking
chain and the assistant's prose live only in the live stream (they vanish on
refresh / history reload).

It checks:
  1. a reasoning summary ``part.done`` event normalizes to ``thinking_complete``
     carrying the full accumulated text;
  2. a text ``content_part.done`` event normalizes to ``text_complete`` carrying
     the full prose, while non-``output_text`` parts produce nothing;
  3. those terminal frames are persistable while the deltas are not;
  4. the resulting timeline item key / segment id matches the live delta, so live
     frames and history replay upsert into the same slot.

Exit code is non-zero if any expectation fails.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from agents.stream_events import RawResponsesStreamEvent  # noqa: E402
from openai.types.responses.response_content_part_done_event import (  # noqa: E402
    ResponseContentPartDoneEvent,
)
from openai.types.responses.response_reasoning_summary_part_done_event import (  # noqa: E402
    ResponseReasoningSummaryPartDoneEvent,
)
from openai.types.responses.response_reasoning_summary_text_delta_event import (  # noqa: E402
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_text_delta_event import (  # noqa: E402
    ResponseTextDeltaEvent,
)

from core.runtime.events import SdkStreamEventNormalizer  # noqa: E402
from core.runtime.timeline import is_persistable, timeline_item_key  # noqa: E402

REASONING_TEXT = "先确认目标可达，再核对鉴权边界，最后构造最小复现。"
ASSISTANT_TEXT = "已确认目标可达；鉴权边界存在越权风险，建议优先修复。"
_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
        return
    _failures.append(name)
    print(f"  FAIL  {name}{f' :: {detail}' if detail else ''}")


def _part_done(text: str, summary_index: int = 0) -> ResponseReasoningSummaryPartDoneEvent:
    return ResponseReasoningSummaryPartDoneEvent.model_validate({
        "item_id": "msg_probe",
        "output_index": 0,
        "summary_index": summary_index,
        "part": {"text": text, "type": "summary_text"},
        "type": "response.reasoning_summary_part.done",
        "sequence_number": 1,
    })


def _delta(text: str) -> ResponseReasoningSummaryTextDeltaEvent:
    return ResponseReasoningSummaryTextDeltaEvent.model_validate({
        "delta": text,
        "item_id": "msg_probe",
        "output_index": 0,
        "summary_index": 0,
        "type": "response.reasoning_summary_text.delta",
        "sequence_number": 1,
    })


def _text_delta(text: str) -> ResponseTextDeltaEvent:
    return ResponseTextDeltaEvent.model_validate({
        "content_index": 0,
        "delta": text,
        "item_id": "msg_text",
        "logprobs": [],
        "output_index": 0,
        "type": "response.output_text.delta",
        "sequence_number": 1,
    })


def _content_part_done(text: str, *, part_type: str = "output_text") -> ResponseContentPartDoneEvent:
    part = (
        {"text": text, "type": "output_text", "annotations": []}
        if part_type == "output_text"
        else {"refusal": text, "type": "refusal"}
    )
    return ResponseContentPartDoneEvent.model_validate({
        "content_index": 0,
        "item_id": "msg_text",
        "output_index": 0,
        "part": part,
        "type": "response.content_part.done",
        "sequence_number": 1,
    })


def main() -> int:
    normalizer = SdkStreamEventNormalizer(segment_scope="selftest")
    now = datetime.now()
    current_agent = "Root Agent"

    # 1) 先到实时分片、后到终态，与真实流顺序一致（顺序反了 segment 会分裂成两块）
    delta_event = normalizer.event_from_sdk_stream(
        RawResponsesStreamEvent(data=_delta(REASONING_TEXT)),
        current_agent,
    )
    check("thinking_delta 归一化为 thinking_delta", str(getattr(delta_event, "type", "")) == "thinking_delta")
    check("thinking_delta 不持久化（仍走实时流）", not is_persistable(delta_event))

    complete = normalizer.event_from_sdk_stream(
        RawResponsesStreamEvent(data=_part_done(REASONING_TEXT)),
        current_agent,
    )
    print(f"[normalize] part.done -> {getattr(complete, 'type', None)}")
    check("reasoning part.done 归一化为 thinking_complete", str(getattr(complete, "type", "")) == "thinking_complete")
    check("thinking_complete 带完整思考文本", getattr(complete, "text", "") == REASONING_TEXT,
          repr(getattr(complete, "text", "")))
    check("thinking_complete 可持久化", is_persistable(complete))

    # 2) 空的 part.done 不应产出事件（避免写入空思考块）
    empty = normalizer.event_from_sdk_stream(RawResponsesStreamEvent(data=_part_done("")), current_agent)
    check("空文本的 part.done 不产出事件", empty is None)

    # 4) 实时 delta 与历史 complete 落在同一个时间线槽位
    delta_key = timeline_item_key(delta_event)
    complete_key = timeline_item_key(complete)
    print(f"[item_key] delta={delta_key} complete={complete_key}")
    check("delta 与 complete 的 item_key 一致（历史回放可覆盖实时帧）", delta_key == complete_key and bool(delta_key))

    # 5) segment_id 也应一致，前端按 segment 聚合不会分裂成两块
    check(
        "delta 与 complete 共用同一 segment_id",
        getattr(delta_event, "segment_id", "x") == getattr(complete, "segment_id", "y"),
    )

    # 6) 正文（助手 prose）与思考链对称：content_part.done 才是正文终态
    text_delta_event = normalizer.event_from_sdk_stream(
        RawResponsesStreamEvent(data=_text_delta(ASSISTANT_TEXT)),
        current_agent,
    )
    check("text_delta 归一化为 text_delta", str(getattr(text_delta_event, "type", "")) == "text_delta")
    check("text_delta 不持久化（仍走实时流）", not is_persistable(text_delta_event))

    text_complete = normalizer.event_from_sdk_stream(
        RawResponsesStreamEvent(data=_content_part_done(ASSISTANT_TEXT)),
        current_agent,
    )
    print(f"[normalize] content_part.done -> {getattr(text_complete, 'type', None)}")
    check("content_part.done 归一化为 text_complete", str(getattr(text_complete, "type", "")) == "text_complete")
    check("text_complete 带完整正文", getattr(text_complete, "text", "") == ASSISTANT_TEXT,
          repr(getattr(text_complete, "text", "")))
    check("text_complete 可持久化", is_persistable(text_complete))
    check(
        "正文 delta 与 complete 的 item_key 一致",
        timeline_item_key(text_delta_event) == timeline_item_key(text_complete)
        and bool(timeline_item_key(text_complete)),
    )
    check(
        "正文 delta 与 complete 共用同一 segment_id",
        getattr(text_delta_event, "segment_id", "x") == getattr(text_complete, "segment_id", "y"),
    )

    # 7) 非 output_text 的 part（如 refusal）不应产出正文终态，避免污染正文流
    refusal = normalizer.event_from_sdk_stream(
        RawResponsesStreamEvent(data=_content_part_done("拒绝作答", part_type="refusal")),
        current_agent,
    )
    check("非 output_text 的 content_part.done 不产出事件", refusal is None)

    print()
    if _failures:
        print(f"thinking-timeline self-test -> FAIL ({len(_failures)} 项未通过)")
        return 1
    print("thinking-timeline self-test -> PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())