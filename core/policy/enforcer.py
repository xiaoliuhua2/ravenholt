"""红线策略的运行时判定：所有出网动作都必须先过这里。

判定顺序（任一命中即拒绝）：
    策略未加载 → kill switch → 绝对红线（DoS）→ 未定义的判定类别 → 禁测清单
    → 目标范围 / 端口 / 内网 → 载荷上限 → 每目标限速 → 全局限速

风险审批项（``src-hunt`` §2，用户可逐项放行）在放行路径上再走人工确认闸：
未放行的审批项命中即改判为「需人工确认」并留下待批准请求。

判定结果会写审计（``audit_events``）。审计写入失败时：
拒绝路径不影响结论；放行路径按 fail-closed 一律改判为拒绝。
"""

from __future__ import annotations

import asyncio
import ipaddress
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from core.policy.approvals import (
    APPROVAL_ACTION_PREFIX,
    READ_ONLY_CATEGORY,
    REDLINE_ACTION_PREFIX,
    REDLINE_CATEGORY,
    GateContext,
    approval_map,
    publish_approval_phase,
)
from core.policy.loader import get_policy, policy_loaded
from core.policy.pending_gate import GateOutcome, pending_gate
from core.policy.rate_limit import limiter
from core.policy.runtime_state import concurrency_guard, denial_window, request_counter
from logger import get_logger
from schema.agent.events import ApprovalPhaseSchema
from schema.policy.policy import ApprovalItem


logger = get_logger(__name__)


# 平台侧可分类的出网动作 → 判定类别。
# 说明：沙箱内命令先由 core.policy.action_signals 按「用户可配置的命中特征」分级：
#   命中绝对红线（DoS）→ redline（硬拒）；
#   命中风险审批项（src-hunt §2）→ 类目就是审批项 key，未放行则进人工确认队列；
#   其余 → read_only，默认放行（仍受 scope / denylist / dos / rate_limit / kill_switch 约束）。
ACTION_CATEGORIES: dict[str, str] = {
    "sandbox.exec": READ_ONLY_CATEGORY,
    # 平台自身对沙箱容器的文件操作 —— 容器内的产物操作，不是对目标的操作，
    # 因此不属 src-hunt §2 的审批项（沙箱内建任务根、写报告正是协议要求的动作）。
    "sandbox.file.write": "sandbox_file",
    "sandbox.file.upload": "sandbox_file",
    "sandbox.file.download": "sandbox_file",
    "evidence.replay": READ_ONLY_CATEGORY,
    "egress.apply": READ_ONLY_CATEGORY,
    "container.create": READ_ONLY_CATEGORY,
}

# 无需审批、也无需匹配审批项表的固定类别（其余未知类别一律 fail-closed 拒绝）。
ALWAYS_ALLOWED_CATEGORIES = frozenset({READ_ONLY_CATEGORY, "sandbox_file"})


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str = "ok"
    reason: str = ""
    action: str = ""
    category: str = ""
    target: str = ""


class PolicyDenied(RuntimeError):
    """动作被红线策略拒绝。"""

    def __init__(self, decision: PolicyDecision) -> None:
        super().__init__(f"[{decision.code}] {decision.reason}")
        self.decision = decision


def _category(action: str) -> str:
    """动作名 → 判定类别（审批项 key / redline / 固定类别）。"""
    if action.startswith(APPROVAL_ACTION_PREFIX):
        return action[len(APPROVAL_ACTION_PREFIX):]
    if action.startswith(REDLINE_ACTION_PREFIX):
        return REDLINE_CATEGORY
    return ACTION_CATEGORIES.get(action, READ_ONLY_CATEGORY)


def _host_of(target: str | None) -> str:
    if not target:
        return ""
    value = target.strip()
    if "://" in value:
        return (urlsplit(value).hostname or "").lower()
    return value.split("/", 1)[0].split(":", 1)[0].lower()


def _port_of(target: str | None) -> int | None:
    if not target:
        return None
    value = target.strip()
    if "://" in value:
        return urlsplit(value).port
    parts = value.split("/", 1)[0].split(":", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def _host_allowed(host: str, allowed: list[str]) -> bool:
    for pattern in allowed:
        candidate = pattern.strip().lower()
        if not candidate:
            continue
        if candidate.startswith("*."):
            candidate = candidate[2:]
        if "/" in candidate:  # CIDR
            try:
                if ipaddress.ip_address(host) in ipaddress.ip_network(candidate, strict=False):
                    return True
            except ValueError:
                continue
            continue
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def evaluate(
    action: str,
    target: str | None = None,
    *,
    payload_bytes: int = 0,
    payload_text: str = "",
) -> PolicyDecision:
    """纯判定，不写审计、不抛异常。"""
    category = _category(action)
    target_text = target or ""

    def deny(code: str, reason: str) -> PolicyDecision:
        return PolicyDecision(False, code, reason, action, category, target_text)

    if not policy_loaded():
        return PolicyDecision(False, "not_loaded", "红线策略未加载", action, "", target_text)

    policy = get_policy()

    if policy.kill_switch.engaged:
        return deny("kill_switch", "急停开关已置位，所有出网动作被拒")

    if category == REDLINE_CATEGORY:
        return deny("redline", "命中绝对红线（DoS）：用户同意也不做")

    # 未定义的类别 fail-closed：避免动作名写错时被当作普通动作静默放行。
    if category not in ALWAYS_ALLOWED_CATEGORIES and category not in approval_map():
        return deny("unknown_category", f"未定义的判定类别 {category}")

    if action.strip().lower() in {item.strip().lower() for item in policy.denylist.actions if item.strip()}:
        return deny("denylist", f"动作 {action} 命中禁测清单")

    host = _host_of(target)
    if host:
        lowered = target_text.lower()
        for pattern in policy.denylist.paths:
            if pattern and pattern.lower() in lowered:
                return deny("denylist", f"目标命中禁测路径规则：{pattern}")

        if policy.scope.allowed_hosts and not _host_allowed(host, policy.scope.allowed_hosts):
            return deny("scope", f"目标 {host} 不在允许范围内")

        port = _port_of(target)
        if policy.scope.allowed_ports and port is not None and port not in policy.scope.allowed_ports:
            return deny("scope", f"端口 {port} 不在允许范围内")

        if policy.scope.deny_private_ranges:
            try:
                if ipaddress.ip_address(host).is_private:
                    return deny("scope", f"目标 {host} 属于内网网段")
            except ValueError:
                pass

    if payload_bytes and payload_bytes > policy.dos.max_payload_bytes:
        return deny("dos", f"载荷 {payload_bytes} 字节超过上限 {policy.dos.max_payload_bytes}")

    if payload_text:
        lowered_payload = payload_text.lower()
        for keyword in policy.denylist.payload_keywords:
            text = keyword.strip().lower()
            if text and text in lowered_payload:
                return deny("denylist", f"载荷命中禁测关键词：{keyword}")

    if host and not limiter.allow(
        f"target:{host}", policy.rate_limit.per_target_per_minute, policy.rate_limit.burst
    ):
        return deny("rate_limit", f"目标 {host} 触发每目标限速")

    if not limiter.allow("global", policy.rate_limit.global_per_minute, policy.rate_limit.burst):
        return deny("rate_limit", "触发全局限速")

    return PolicyDecision(True, "ok", "", action, category, target_text)


async def _apply_confirmation_gate(
    action: str,
    decision: PolicyDecision,
    *,
    gate_context: GateContext | None = None,
) -> PolicyDecision:
    """命中未放行的审批项时检查许可；未获许可时**挂起等用户决策**或立即拦下。

    ``gate_context is None``（平台侧手工执行、证据复放、容器创建等路径）保持原语义：
    立即返回 ``confirmation_required``、**不挂起**。判定只能用这个显式开关，不能用
    「是否有 session_id」之类的隐式条件，否则其它调用方会被误挂住。
    """
    if decision.category in ALWAYS_ALLOWED_CATEGORIES:
        return decision
    item = approval_map().get(decision.category)
    if item is None or item.allow:
        return decision

    from service.policy.confirmations import resolve_confirmation

    granted, pending_id = await resolve_confirmation(
        action=action,
        category=decision.category,
        target=decision.target,
    )
    if granted:
        return decision

    if gate_context is None or pending_id is None:
        return PolicyDecision(
            False,
            "confirmation_required",
            f"动作 {action} 命中审批项「{item.label}」，需人工确认（待批准请求 id={pending_id}）",
            action,
            decision.category,
            decision.target,
        )

    return await _suspend_for_approval(
        action, decision, item, pending_id, gate_context=gate_context
    )


def _approval_wait_seconds() -> float | None:
    """挂起时长（秒）；策略未加载或配为 0 时返回 None（无限等待）。"""
    if not policy_loaded():
        return None
    seconds = get_policy().approval_wait_seconds
    return float(seconds) if seconds > 0 else None


def _request_reject_confirmation_detached(confirmation_id: int, note: str) -> None:
    """另起任务把挂起记录置为拒绝（取消路径用，不在 cancelling 状态下 await DB）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _reject() -> None:
        try:
            from service.policy.confirmations import reject_pending_confirmation

            await reject_pending_confirmation(confirmation_id, note=note)
        except Exception:  # noqa: BLE001 - 清理失败不应影响中断语义
            logger.exception("审批记录置终态失败 id=%s", confirmation_id)

    loop.create_task(_reject())


async def _suspend_for_approval(
    action: str,
    decision: PolicyDecision,
    item: ApprovalItem,
    confirmation_id: int,
    *,
    gate_context: GateContext,
) -> PolicyDecision:
    """挂起等待用户决策，再决定本次动作是否放行。

    顺序固定为「先建记录 → 再发事件 → 最后 await」，避免「卡片刚出现就被点批准」
    丢唤醒。挂起发生在工具调用之前、并发租约之外，因此不占并发额度、也不受沙箱命令
    超时约束。
    """
    pending_gate.open(confirmation_id, session_id=gate_context.session_id)
    published = publish_approval_phase(
        gate_context,
        confirmation_id=confirmation_id,
        item=item,
        action=action,
        target=decision.target,
        phase=ApprovalPhaseSchema.PENDING,
        message=f"该动作命中审批项「{item.label}」，需要你确认后才会执行。",
    )
    if not published:
        # 卡片送不到界面（会话未 pooled / 时间线未就绪）：不挂起，立即拦下并说明。
        pending_gate.discard(confirmation_id)
        return PolicyDecision(
            False,
            "confirmation_required",
            f"动作 {action} 命中审批项「{item.label}」，需人工确认（待批准请求 id={confirmation_id}）",
            action,
            decision.category,
            decision.target,
        )

    try:
        outcome = await pending_gate.wait(confirmation_id, timeout=_approval_wait_seconds())
    except BaseException:
        # CancelledError（用户中断回合）属 BaseException，普通 except Exception 兜不住。
        # 这里只能做同步清理，DB 落终态交给 detached task（cancelling 状态下不能 await）。
        pending_gate.discard(confirmation_id)
        publish_approval_phase(
            gate_context,
            confirmation_id=confirmation_id,
            item=item,
            action=action,
            target=decision.target,
            phase=ApprovalPhaseSchema.CANCELLED,
            message="回合已中断，本次审批作废。",
        )
        _request_reject_confirmation_detached(confirmation_id, "Discarded by turn interrupt.")
        raise

    if outcome == GateOutcome.APPROVED:
        publish_approval_phase(
            gate_context,
            confirmation_id=confirmation_id,
            item=item,
            action=action,
            target=decision.target,
            phase=ApprovalPhaseSchema.APPROVED,
            message="已批准，本次动作继续执行。",
        )
        await _consume_once_permit(confirmation_id)
        return decision

    if outcome == GateOutcome.TIMEOUT:
        publish_approval_phase(
            gate_context,
            confirmation_id=confirmation_id,
            item=item,
            action=action,
            target=decision.target,
            phase=ApprovalPhaseSchema.TIMEOUT,
            message=f"等待 {int(_approval_wait_seconds() or 0)} 秒未确认，已按拒绝处理。",
        )
        _request_reject_confirmation_detached(confirmation_id, "Approval wait timed out.")
        detail = "等待超时，已按拒绝处理"
    else:
        publish_approval_phase(
            gate_context,
            confirmation_id=confirmation_id,
            item=item,
            action=action,
            target=decision.target,
            phase=ApprovalPhaseSchema.REJECTED,
            message="已拒绝，本次动作未执行。",
        )
        detail = "已被拒绝"

    return PolicyDecision(
        False,
        "confirmation_required",
        f"动作 {action} 命中审批项「{item.label}」：{detail}",
        action,
        decision.category,
        decision.target,
    )


async def _consume_once_permit(confirmation_id: int) -> None:
    """本次已用掉这次批准：``once`` 许可立即消费，避免下一次命中又白拿一次放行。"""
    try:
        from service.policy.confirmations import consume_once_permit

        await consume_once_permit(confirmation_id)
    except Exception:  # noqa: BLE001 - 消费失败不影响本次放行结论
        logger.exception("消费一次性许可失败 id=%s", confirmation_id)


async def enforce(
    action: str,
    target: str | None = None,
    *,
    payload_bytes: int = 0,
    payload_text: str = "",
    actor: str = "",
    detail: dict[str, Any] | None = None,
    gate_context: GateContext | None = None,
) -> PolicyDecision:
    """判定 + 审计。返回判定结果，由调用方决定如何拒绝。

    ``gate_context`` 只在「智能体发起的沙箱命令」这条路径上传入；其余调用方不传，
    于是命中未放行审批项时依旧是「立即拦下」，行为与改造前完全一致。
    """
    decision = evaluate(
        action, target, payload_bytes=payload_bytes, payload_text=payload_text
    )

    if decision.allowed and policy_loaded():
        policy = get_policy()
        # 总量封顶：进程内计数，策略 revision 变化或进程重启即归零。
        if not request_counter.check_and_increment(policy.dos.max_requests_total, policy.revision):
            decision = PolicyDecision(
                False, "dos",
                f"总请求量已达上限 {policy.dos.max_requests_total}",
                action, decision.category, decision.target,
            )

    # 延迟导入：避免 core → service 的导入环
    from service.audit.store import record_audit_event

    if decision.allowed:
        decision = await _apply_confirmation_gate(action, decision, gate_context=gate_context)

    if not decision.allowed:
        _maybe_auto_engage(decision)

    revision = get_policy().revision if policy_loaded() else 0
    try:
        await record_audit_event(
            action=action,
            category=decision.category,
            target=decision.target,
            decision="allow" if decision.allowed else "deny",
            code=decision.code,
            reason=decision.reason,
            policy_revision=revision,
            actor=actor,
            detail=detail or {},
        )
    except Exception as exc:  # noqa: BLE001 - 审计失败必须走 fail-closed 判断
        if decision.allowed:
            logger.exception("审计写入失败，按 fail-closed 改判为拒绝：%s", action)
            return PolicyDecision(
                False, "audit_failed", f"审计写入失败，按 fail-closed 拒绝：{exc}",
                action, decision.category, decision.target,
            )
        logger.exception("审计写入失败（拒绝路径，结论不变）：%s", action)

    return decision


def _concurrency_key(target: str | None) -> str:
    host = _host_of(target)
    return host or "global"


@asynccontextmanager
async def policy_guard(
    action: str,
    target: str | None = None,
    *,
    payload_bytes: int = 0,
    payload_text: str = "",
    actor: str = "",
    detail: dict[str, Any] | None = None,
    gate_context: GateContext | None = None,
):
    """判定通过后，按「单目标并发上限」持有租约执行真实动作。

    并发是占用状态，必须包住真实动作才有意义（只判定不包裹 = 立刻释放 = 形同虚设）。
    ``dos.max_concurrency_per_target <= 0`` 表示不限。

    ``gate_context`` 传入时，命中未放行审批项会**先挂起等待用户决策，再决定是否放行**；
    因为挂起发生在取租约之前，等待期间不占并发额度。
    """
    decision = await enforce(
        action,
        target,
        payload_bytes=payload_bytes,
        payload_text=payload_text,
        actor=actor,
        detail=detail,
        gate_context=gate_context,
    )
    if not decision.allowed:
        raise PolicyDenied(decision)

    limit = get_policy().dos.max_concurrency_per_target if policy_loaded() else 0
    if limit <= 0:
        yield decision
        return

    semaphore = concurrency_guard.semaphore(_concurrency_key(target), limit)
    async with semaphore:
        yield decision


# ── 自动急停：越界类拒绝在窗口内达阈值时自动上锁（只上锁，绝不自动解除） ──────

_AUTO_ENGAGE_CODES = frozenset({"scope", "denylist", "dos"})
_AUTO_ENGAGE_MIN_THRESHOLD = 3
_auto_engage_running = False


def _maybe_auto_engage(decision: PolicyDecision) -> None:
    global _auto_engage_running
    if decision.code not in _AUTO_ENGAGE_CODES or not policy_loaded():
        return
    policy = get_policy()
    threshold = policy.kill_switch.max_audit_denials_before_engage
    if threshold < _AUTO_ENGAGE_MIN_THRESHOLD or policy.kill_switch.engaged or _auto_engage_running:
        return
    if denial_window.record() < threshold:
        return

    async def _engage() -> None:
        global _auto_engage_running
        try:
            from service.policy.config import set_kill_switch

            await set_kill_switch(True, actor="system:auto_engage")
            logger.warning("越界类拒绝在窗口内达阈值 %s，已自动置位急停开关", threshold)
        except Exception:  # noqa: BLE001 - 后台任务失败只记录
            logger.exception("自动置位急停失败")
        finally:
            _auto_engage_running = False

    _auto_engage_running = True
    try:
        asyncio.get_running_loop().create_task(_engage())
    except RuntimeError:
        # 无运行中的事件循环（不应发生）：放弃本轮自动置位
        _auto_engage_running = False
