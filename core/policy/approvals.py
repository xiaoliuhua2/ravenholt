"""风险审批项（``src-hunt`` 的 ``SKILL.md`` §2「安全红线与授权」）的读取与渲染。

审批项本身定义在策略文件的 ``approvals`` 里（用户可配），本模块做三件事：

- 给判定链路提供 ``key → 审批项`` 查表（:func:`approval_map`）；
- 给系统提示词渲染「本次会话的授权状态」（:func:`render_approval_discipline`），
  让控制台上拨动的开关真正约束智能体行为，而不是只留在配置文件里；
- 构造「审批挂起」期间的会话事件（:class:`GateContext` / :func:`publish_approval_phase`），
  让对话流里出现一条可操作的审批卡片。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from core.policy.loader import get_policy, policy_loaded
from schema.agent.events import AgentEventSchema, ApprovalEvent, ApprovalPhaseSchema
from schema.policy.policy import ApprovalItem


# 判定用的三个保留类别：普通动作、绝对红线，以及「审批项」的动作名前缀。
READ_ONLY_CATEGORY = "read_only"
REDLINE_CATEGORY = "redline"
APPROVAL_ACTION_PREFIX = "sandbox.exec.approval."
REDLINE_ACTION_PREFIX = "sandbox.exec.redline."


@dataclass(frozen=True)
class GateContext:
    """挂起等待用户审批所需的会话上下文，由闸口装配层（sandbox_provision）注入。

    策略层只依赖 ``session_id`` 与 ``publish`` 两个字段，**不 import 运行时模块**，
    因此不会形成 ``core.policy → core.runtime`` 的循环依赖。
    """

    session_id: str
    publish: Callable[[AgentEventSchema], bool]


def approval_map() -> dict[str, ApprovalItem]:
    """当前策略里的审批项（``key`` → 条目）；策略未加载时返回空表。"""
    if not policy_loaded():
        return {}
    return {item.key: item for item in get_policy().approvals}


def build_approval_event(
    *,
    confirmation_id: int,
    item: ApprovalItem,
    action: str,
    target: str,
    phase: ApprovalPhaseSchema,
    message: str = "",
) -> ApprovalEvent:
    """构造一条审批事件（``seq`` 由事件总线盖章，时间线 key 为 ``approval:<id>``）。"""
    return ApprovalEvent(
        created_at=datetime.now(),
        confirmation_id=confirmation_id,
        approval_key=item.key,
        label=item.label,
        action=action,
        target=target,
        phase=phase,
        message=message,
    )


def publish_approval_phase(
    gate_context: GateContext,
    *,
    confirmation_id: int,
    item: ApprovalItem,
    action: str,
    target: str,
    phase: ApprovalPhaseSchema,
    message: str = "",
) -> bool:
    """把审批阶段推入会话事件总线；返回是否被成功接收。

    会话未 pooled（或时间线尚未就绪）时返回 ``False`` —— 调用方据此降级为
    「立即告知需审批」而不是挂起，避免出现「界面看不到卡片却一直等」的死等。
    """
    event = build_approval_event(
        confirmation_id=confirmation_id,
        item=item,
        action=action,
        target=target,
        phase=phase,
        message=message,
    )
    try:
        return bool(gate_context.publish(event))
    except Exception:  # noqa: BLE001 - 推事件失败不应改变策略结论
        return False


# 放行区的条目描述里若残留「默认不做 / 须你同意」这类**闸门语义**，会与表头自相矛盾。
# 实测（2026-10-15 会话 da21d1df）：表头写「已放行、不必再逐条征求同意」，条目正文却仍写
# 「默认不做，须你同意」→ 模型于是又在对话里向用户索要了一次确认。这里把这些句子剥掉，
# 只保留动作本身的技术说明与操作纪律（如「改密不自己动手」）。
_GATE_SENTENCES = (
    re.compile(r"默认不做[，,;；]?\s*须你同意[；;。]?"),
    re.compile(r"默认不做[；;。]"),
    re.compile(r"须你(?:明确)?同意[；;。]?"),
    re.compile(r"同意前会先说明载荷、会发生什么、副作用影响面、中止与善后[。；;]?"),
    re.compile(r"同意后按最小伤害顺序执行[。；;]?"),
)


def _granted_description(description: str) -> str:
    """去掉条目描述里「等你点头」的闸门语义（放行区表头已说明不必再等确认）。"""
    text = description or ""
    for pattern in _GATE_SENTENCES:
        text = pattern.sub("", text)
    text = re.sub(r"[，,;；]\s*(?=[，,;；。])", "", text)
    return text.strip().strip("，,;；。：:")


def render_approval_discipline() -> str:
    """系统提示词用的「授权状态」块；策略未加载时返回空串。"""
    if not policy_loaded():
        return ""

    items = get_policy().approvals
    granted = [item for item in items if item.allow]
    withheld = [item for item in items if not item.allow]

    lines = [
        "# 授权状态（用户在控制台逐项确认过，以本段为准）",
        "- **绝对红线**：DoS 同意也不做，任何理由都不执行；"
        "发现某输入会打崩服务 → 立即停止复现、记录现象、不再碰它。",
    ]
    if granted:
        lines.append(
            "- **用户已放行**（**不必再等用户确认**；执行前用一句话说明要做什么、载荷与影响即可；"
            "仍须最小伤害、只读优先、单发低量）："
        )
        lines.extend(
            f"  - {item.label}：{_granted_description(item.description) or '已获放行'}"
            for item in granted
        )
    if withheld:
        lines.append(
            "- **未放行（须用户点头才可做）**：确需执行时**直接发起该动作** —— 平台会自动在会话里"
            "弹出一张**审批卡片**，用户点「同意」后命令继续执行（等待上限见 ``approval_wait_seconds``，"
            "不打断本次测试）；**不要用纯文本向用户索要确认**（非交互模式下纯文本请求会被忽略、白等）。"
            "命令文本判不出特征的项（``signals`` 为空，如越权写）**先不要执行**：把该动作、理由与影响"
            "写进结论，等用户在**下一轮消息**里明确同意后再做 —— 本平台是回合制，没有「原地等用户」的工具，"
            "调用 ``wait_for_user`` 只会得到「没有用户在线」的拒绝。"
        )
        lines.extend(f"  - {item.label}：{item.description}" for item in withheld)
    else:
        lines.append(
            "- 除绝对红线外，其余动作均已被用户放行；**执行前用一句话声明即可，不必再等用户确认**。"
        )
    return "\n".join(lines)


__all__ = [
    "APPROVAL_ACTION_PREFIX",
    "GateContext",
    "READ_ONLY_CATEGORY",
    "REDLINE_ACTION_PREFIX",
    "REDLINE_CATEGORY",
    "approval_map",
    "build_approval_event",
    "publish_approval_phase",
    "render_approval_discipline",
]
