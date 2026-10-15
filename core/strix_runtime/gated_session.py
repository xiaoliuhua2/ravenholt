"""红线闸口：把 ravenholt 的策略判定挂到 SDK 沙箱会话上。

接入 strix 原生能力后，命令与文件写入改由 SDK 的 ``Shell`` / ``Filesystem`` 能力经
``session.exec`` / ``session.pty_exec_start`` / ``session.write`` 等直接下发到容器，
绕过了 ravenholt 原先在 ``service/sandbox/commands.py`` 的收口。本模块用「子类 + 运行时
重绑 ``__class__``」把闸口挂回会话（**不改 vendor 代码**）；判定口径与
``service/sandbox/commands.py`` 保持一致：``classify_sandbox_command`` 分级 →
``policy_guard`` 判定并持有并发租约 → 拒绝时抛 ``PolicyDenied``。
"""

from __future__ import annotations

import io
import logging
from typing import Any

from agents.sandbox.session.sandbox_session import SandboxSession

from core.policy.action_signals import CONTENT_SCOPE, EXEC_SCOPE, classify_sandbox_command
from core.policy.approvals import GateContext
from core.policy.enforcer import policy_guard


logger = logging.getLogger(__name__)

# 参与判定的文件正文上限：避免把大文件整体塞进策略匹配。
_MAX_GATE_TEXT_CHARS = 200_000


def _command_text(command: tuple[Any, ...]) -> str:
    return " ".join(str(part) for part in command).strip()


def _stream_text(data: io.IOBase) -> str:
    """尽量不移动读写指针地取正文；取不到时返回空串（此时只判定路径）。"""
    getvalue = getattr(data, "getvalue", None)
    if not callable(getvalue):
        return ""
    try:
        value = getvalue()
    except Exception:  # noqa: BLE001 - 取值失败按空正文处理，不阻断写入本身
        return ""
    if isinstance(value, bytes | bytearray):
        return bytes(value).decode("utf-8", errors="replace")[:_MAX_GATE_TEXT_CHARS]
    if isinstance(value, str):
        return value[:_MAX_GATE_TEXT_CHARS]
    return ""


_TARGET_STOP_CHARS = (" ", "\t", "\n", '"', "'", "`", ">", "<", "|", ";", "&", ")")


def _extract_target(text: str) -> str | None:
    """从命令文本里抽出显式 http(s) 目标（``host[:port][/path]``）；抽不到返回 None。

    只认最可靠的形态（完整 URL），不做正则硬造，避免把无关字符串误判成目标而误伤。
    抽不到时权威判定位是网络层白名单，这里只是尽力而为。
    """
    lowered = text.lower()
    for scheme in ("https://", "http://"):
        index = lowered.find(scheme)
        if index < 0:
            continue
        rest = text[index + len(scheme):]
        for stop in _TARGET_STOP_CHARS:
            cut = rest.find(stop)
            if cut >= 0:
                rest = rest[:cut]
        candidate = rest.strip().rstrip("/")
        if candidate:
            return candidate
    return None


class GatedSandboxSession(SandboxSession):
    """带红线闸口的沙箱会话；其余行为完全沿用 ``SandboxSession`` 的委托实现。

    实例不由构造器产生，而是由 :func:`bind_policy_gate` 在运行时把既有
    ``SandboxSession`` 实例的 ``__class__`` 换成本类（与会话自身重绑 ``_inner`` 是同一手法），
    因此不丢任何已有状态、也不需要重建会话。

    被拦截的入口（其余全部透传）：

    - ``exec`` / ``pty_exec_start``：命令文本（``scope=exec``，红线 + 审批全判）
    - ``pty_write_stdin``：写入 stdin 的字符（并回带该 PTY 会话的原始命令）
    - ``write`` / ``rm`` / ``mkdir``：文件写入与删除；``apply_patch`` 经这三个方法落地。
      这三个按 ``scope=content`` 判定——只做审批，**豁免绝对红线 DoS**，避免 agent 在
      文件正文 / 报告里正当提及 DoS 工具名被硬拒。

    每个入口都用 ``policy_guard`` 包裹真实动作：既做判定，也在判定通过后按
    「单目标并发上限」持有租约（并发是占用状态，不包裹就等于没限）。
    """

    _pty_command_ledger: dict[int, str]

    def _gate_context(self) -> GateContext | None:
        """会话上下文（session_id + 事件发布回调）齐备时才允许「挂起等审批」。

        缺任一项（例如未走装配层绑定的会话）就返回 None，策略层按「立即拦下」处理，
        避免出现「卡片送不到界面却一直等」的死等。
        """
        session_id = getattr(self, "_gate_session_id", "")
        publisher = getattr(self, "_gate_publisher", None)
        if not session_id or not callable(publisher):
            return None
        return GateContext(session_id=session_id, publish=publisher)

    def _guard(
        self,
        text: str,
        *,
        op: str,
        extra: dict[str, Any] | None = None,
        scope: str = EXEC_SCOPE,
    ):
        # scope=content（文件正文，apply_patch 经 write 落地）豁免绝对红线 DoS，
        # 只做审批判定；可执行命令路径用 exec 作用域。
        action, basis = classify_sandbox_command(text, scope=scope)
        # 审计里带上操作内容，便于复盘被拦截的高风险操作。
        detail: dict[str, Any] = {
            "op": op,
            "surface": "strix-sandbox-session",
            "command": text[:1000],
            "scope": scope,
        }
        if extra:
            detail.update(extra)
        if basis:
            detail["match"] = basis
        target = _extract_target(text)
        if target:
            detail["target"] = target
        else:
            # 抽不到显式目标：命令层不做范围判定，权威交给网络层白名单。
            detail["target_unknown"] = True
        return policy_guard(
            action,
            target,
            payload_bytes=len(text.encode("utf-8")),
            payload_text=text,
            detail=detail,
            gate_context=self._gate_context(),
        )

    async def exec(  # type: ignore[override]
        self,
        *command: Any,
        timeout: float | None = None,
        shell: bool | list[str] = True,
        user: Any = None,
    ) -> Any:
        async with self._guard(_command_text(command), op="exec"):
            return await super().exec(*command, timeout=timeout, shell=shell, user=user)

    async def pty_exec_start(  # type: ignore[override]
        self,
        *command: Any,
        timeout: float | None = None,
        shell: bool | list[str] = True,
        user: Any = None,
        tty: bool = False,
        yield_time_s: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        text = _command_text(command)
        if text:
            async with self._guard(text, op="pty_exec_start"):
                update = await super().pty_exec_start(
                    *command,
                    timeout=timeout,
                    shell=shell,
                    user=user,
                    tty=tty,
                    yield_time_s=yield_time_s,
                    max_output_tokens=max_output_tokens,
                )
        else:
            update = await super().pty_exec_start(
                *command,
                timeout=timeout,
                shell=shell,
                user=user,
                tty=tty,
                yield_time_s=yield_time_s,
                max_output_tokens=max_output_tokens,
            )

        process_id = getattr(update, "process_id", None)
        if text and isinstance(process_id, int):
            # 记账：write_stdin 只有 process_id，需要回带原始命令才能判定上下文。
            self._pty_command_ledger[process_id] = text
        return update

    async def pty_write_stdin(  # type: ignore[override]
        self,
        *,
        session_id: int,
        chars: str,
        yield_time_s: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        if not chars:
            return await super().pty_write_stdin(
                session_id=session_id,
                chars=chars,
                yield_time_s=yield_time_s,
                max_output_tokens=max_output_tokens,
            )
        origin = self._pty_command_ledger.get(session_id, "")
        extra = {"pty_command": origin[:2000]} if origin else None
        async with self._guard(chars, op="pty_write_stdin", extra=extra):
            return await super().pty_write_stdin(
                session_id=session_id,
                chars=chars,
                yield_time_s=yield_time_s,
                max_output_tokens=max_output_tokens,
            )

    async def write(  # type: ignore[override]
        self,
        path: Any,
        data: io.IOBase,
        *,
        user: Any = None,
    ) -> None:
        text = _stream_text(data)
        async with self._guard(
            text, op="write", extra={"path": str(path)}, scope=CONTENT_SCOPE
        ):
            return await super().write(path, data, user=user)

    async def rm(  # type: ignore[override]
        self,
        path: Any,
        *,
        recursive: bool = False,
        user: Any = None,
    ) -> None:
        flag = " -rf" if recursive else ""
        async with self._guard(
            f"rm{flag} {path}", op="rm", extra={"path": str(path)}, scope=CONTENT_SCOPE
        ):
            return await super().rm(path, recursive=recursive, user=user)

    async def mkdir(  # type: ignore[override]
        self,
        path: Any,
        *,
        parents: bool = False,
        user: Any = None,
    ) -> None:
        flag = " -p" if parents else ""
        async with self._guard(
            f"mkdir{flag} {path}", op="mkdir", extra={"path": str(path)}, scope=CONTENT_SCOPE
        ):
            return await super().mkdir(path, parents=parents, user=user)


def bind_policy_gate(
    session: Any,
    *,
    session_id: str = "",
    publisher: Any = None,
) -> Any:
    """把 ``session`` 的运行时类换成 :class:`GatedSandboxSession`（幂等）。

    只接受 SDK 的 ``SandboxSession``；传入其它对象直接报错，避免把闸口静默漏挂。

    ``session_id`` 与 ``publisher`` 是「命中未放行审批项时挂起等用户决策」所需的会话
    上下文：只有装配层（``sandbox_provision``）知道 ravenholt 的 session_id，而事件
    发布要经 ``AgentSessionPool.publish``，故由它注入，策略层只依赖回调、不 import 运行时。
    两者缺任一项时闸口照旧工作，只是命中审批项时立即拦下（不再挂起）。
    """
    if isinstance(session, GatedSandboxSession):
        return session
    if not isinstance(session, SandboxSession):
        raise TypeError(
            f"cannot bind policy gate to {type(session).__name__}: expected SandboxSession"
        )
    session.__class__ = GatedSandboxSession
    session._pty_command_ledger = {}
    session._gate_session_id = session_id
    session._gate_publisher = publisher
    logger.info("policy gate bound to sandbox session %s", getattr(session.state, "session_id", "?"))
    return session


__all__ = ["GatedSandboxSession", "bind_policy_gate"]
