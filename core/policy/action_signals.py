"""沙箱命令的动作分级（``src-hunt`` §2 的机制化）。

目的：把红线纪律从**提示词**变成**机制**。

判定顺序（命中即返回，越靠前越严）：

1. **绝对红线 DoS**（§2.2，同意也不做）→ 硬拒；
2. **风险审批项**（§2 的其余条目，逐项可放行）→ 未放行则进人工确认队列；
3. 未命中任何特征 → 普通沙箱命令，默认放行。

命中特征都定义在策略文件里（``redline.dos_signals`` 与 ``approvals[].signals``），
用户可自定义。**只做保守升级**：命中明确特征才改变类别，其余一律留在普通命令，
避免误伤 src-hunt 协议要求的常规动作（建任务根、抽 JS、装依赖、写报告）。

匹配语义（消除子串误报）：

- **裸词特征**（纯 ``[a-z0-9]``，如 ``hoic``）两侧加词边界 ⇒ ``choices`` 不再命中 ``hoic``；
- **多词特征**（含空格/符号，如 ``ping -f``）加**左侧**词边界 ⇒ ``tcping -f`` 不再命中
  ``ping -f``，同时 ``ab -n 10000000`` 这类阈值上探仍能命中；
- **``+`` 复合特征**：各段须**同时**命中（AND）⇒ ``-x post +/logout`` 只在真的发起
  登出请求时命中，被动 ``grep`` / 读日志不会；
- **作用域**：``scope="content"``（文件正文 / 笔记 / 报告）**豁免绝对红线 DoS**，
  避免 agent 在文档里正当提及工具名被硬拒。
"""

from __future__ import annotations

import re

from core.policy.approvals import APPROVAL_ACTION_PREFIX, REDLINE_ACTION_PREFIX
from core.policy.loader import get_policy, policy_loaded


BASE_ACTION = "sandbox.exec"
# 绝对红线：DoS（唯一「同意也不做」的动作红线，见 src-hunt §2.2）。
DOS_REDLINE_ACTION = f"{REDLINE_ACTION_PREFIX}dos"

# 判定作用域：exec = 可执行命令（红线 + 审批全判）；content = 文件/报告正文（豁免红线）。
EXEC_SCOPE = "exec"
CONTENT_SCOPE = "content"

# 左侧词边界 / 右（裸词）词边界，详见模块 docstring 的匹配语义。
_LEFT_SEP = r"(?<![a-z0-9])"
_RIGHT_SEP = r"(?![a-z0-9])"
_BARE_TOKEN = re.compile(r"[a-z0-9]+\Z")


def _part_hit(part: str, lowered: str) -> bool:
    """单个特征段命中判定。

    - 段首是**字母/数字**时才加**左侧**词边界（避免作为更长词的后缀被误命中，
      如 ``ping -f`` 不应命中 ``tcping -f``）；段首是符号/空格（如 ``/logout``、
      ``--flood``）则不加左侧边界——否则 ``/logout`` 会漏掉 ``/api/logout``。
    - 裸词（纯 ``[a-z0-9]``）额外要求右侧词边界（``hoic`` 不应命中 ``choices``）。
    """
    pattern = re.escape(part)
    if part[:1].isalnum():
        pattern = _LEFT_SEP + pattern
    if _BARE_TOKEN.fullmatch(part):
        pattern = pattern + _RIGHT_SEP
    return re.search(pattern, lowered) is not None


def _signal_hit(signal: str, lowered: str) -> bool:
    """特征命中判定；``+`` 表示复合特征（各段须同时命中）。"""
    text = signal.strip().lower()
    if not text:
        return False
    parts = [p.strip() for p in text.split("+") if p.strip()]
    return bool(parts) and all(_part_hit(p, lowered) for p in parts)


def classify_sandbox_command(command: str, *, scope: str = EXEC_SCOPE) -> tuple[str, str]:
    """返回 ``(动作名, 命中依据)``；未命中任何特征时返回 ``(sandbox.exec, "")``。

    ``scope="content"`` 用于文件正文 / 笔记 / 报告等**非可执行**载荷：只做审批判定，
    **豁免绝对红线 DoS**——否则 agent 在文档里正当提及 hping3 / slowloris 等工具名
    会被硬拒（见 2026-10-15 会话 5 次 apply_patch 误拦复盘）。
    """
    if not policy_loaded():
        return BASE_ACTION, ""

    policy = get_policy()
    lowered = command.lower()

    if scope != CONTENT_SCOPE:
        for signal in policy.redline.dos_signals:
            if _signal_hit(signal, lowered):
                return DOS_REDLINE_ACTION, f"绝对红线 DoS：{signal}"

    for item in policy.approvals:
        for signal in item.signals:
            if _signal_hit(signal, lowered):
                return f"{APPROVAL_ACTION_PREFIX}{item.key}", f"{item.label}：{signal}"
    return BASE_ACTION, ""


__all__ = [
    "BASE_ACTION",
    "DOS_REDLINE_ACTION",
    "EXEC_SCOPE",
    "CONTENT_SCOPE",
    "classify_sandbox_command",
]
