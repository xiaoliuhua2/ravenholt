"""事件总线旁路归档器：把全量原始事件 append-only 落盘。

**为什么需要它**：REST ``/agent-sessions/{sid}/events`` 只回放 ``is_persistable`` 的事件
（见 ``core.runtime.timeline``）—— 逐字思考 / 正文增量、运行状态切换等帧从不落库。
任何「轮询快照式」的外部监控因此永远拿不到「逐字过程」。归档器挂在事件出口，
在持久化过滤**之前**无条件写全量帧（含 delta 与控制帧），是外部聚合器唯一能拿到
「全部过程」的位置。

**写盘模型**：热路径只做一次 O(1) 入队（无 IO、无锁竞争），后台守护线程批量落盘。
任何异常都静默降级 —— 归档失败绝不阻断主流程（用户仍看得到实时输出）；队列积压超过
上限则丢弃并计数，宁可丢归档也不拖垮运行时。

**落盘布局**（append-only，按会话 / 小时分片）::

    <WORKSPACE>/archive/<session_id>/<yyyymmdd-hh>.jsonl

每行一条 JSON 记录，``kind`` 区分来源：

- ``{"kind": "event", "ts", "seq", "type", "event": {...}}`` 事件总线原始帧
- ``{"kind": "llm",   "ts", "agent_id", "agent_name", "record": {...}}`` LLM 请求/响应原文
"""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import WORKSPACE, get_config
from logger import get_logger


logger = get_logger(__name__)

ARCHIVE_ROOT = WORKSPACE / "archive"

_DELTA_TYPES = frozenset({"text_delta", "thinking_delta"})
_FLUSH_INTERVAL_SECONDS = 1.0
_FLUSH_MAX_LINES = 512
_SWEEP_INTERVAL_SECONDS = 3600.0

_queue: queue.Queue[tuple[str, str]] | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()
_dropped = 0


def _safe_segment(name: str) -> str:
    """把会话 id 收敛成安全的目录名（会话 id 正常是十六进制串，防御性处理）。"""
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name)
    return cleaned or "unknown"


def _shard_name() -> str:
    return datetime.now().strftime("%Y%m%d-%H")


def _ensure_writer() -> queue.Queue[tuple[str, str]] | None:
    """惰性启动后台写线程；任何失败都返回 None（调用方静默降级）。"""
    global _queue, _thread
    if _queue is not None:
        return _queue
    try:
        with _lock:
            if _queue is None:
                cfg = get_config().archive
                q: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=int(cfg.queue_max))
                t = threading.Thread(
                    target=_writer_loop,
                    args=(q,),
                    name="ravenholt-archive-writer",
                    daemon=True,
                )
                t.start()
                _queue = q
                _thread = t
        return _queue
    except Exception:  # noqa: BLE001 - 归档不可用不得影响主流程
        logger.debug("archive writer unavailable", exc_info=True)
        return None


def _enqueue_line(session_id: str, line: str) -> None:
    global _dropped
    q = _ensure_writer()
    if q is None:
        return
    try:
        q.put_nowait((session_id, line))
    except queue.Full:
        _dropped += 1
        if _dropped % 1000 == 1:
            logger.warning("archive queue full, dropped=%s", _dropped)
    except Exception:  # noqa: BLE001
        logger.debug("archive enqueue failed", exc_info=True)


def archive_event(session_id: str, event: Any) -> None:
    """把一条事件总线原始帧追加进归档队列（热路径：绝不阻塞、绝不抛异常）。"""
    try:
        cfg = get_config().archive
        if not cfg.enabled:
            return
        event_type = str(getattr(event, "type", ""))
        if event_type in _DELTA_TYPES:
            if not cfg.capture_deltas:
                return
            if event_type == "thinking_delta" and not cfg.capture_thinking_delta:
                return
            if event_type == "text_delta" and not cfg.capture_text_delta:
                return
        # delta 帧的 ``text`` 字段是「累积全文快照」——每个增量帧把当前完整思考
        # 重发一遍，完整内容已由 thinking_complete / text_complete 承载。归档副本
        # 剥除该字段可去掉约三个数量级的冗余（实测冗余 1608 倍，单回合省数 GB）。
        # 只裁剪归档副本，不改事件模型，实时流与前端渲染不受影响。
        if event_type in _DELTA_TYPES:
            payload = event.model_dump_json(exclude={"text"})
        else:
            payload = event.model_dump_json()
        head = json.dumps(
            {
                "kind": "event",
                "ts": datetime.now().isoformat(timespec="milliseconds"),
                "seq": getattr(event, "seq", None),
                "type": event_type,
            },
            ensure_ascii=False,
        )
        # head 是完整 JSON 对象，去掉尾部 '}' 后拼接事件原文，避免二次解析。
        _enqueue_line(session_id, head[:-1] + ',"event":' + payload + "}")
    except Exception:  # noqa: BLE001
        logger.debug("archive event skipped", exc_info=True)


def archive_llm_call(session_id: str, record: dict[str, Any]) -> None:
    """把一次 LLM 调用的请求/响应原文追加进归档队列。"""
    try:
        cfg = get_config().archive
        if not cfg.enabled or not cfg.capture_llm_bodies:
            return
        payload = dict(record)
        payload.setdefault("ts", datetime.now().isoformat(timespec="milliseconds"))
        payload["kind"] = "llm"
        _enqueue_line(session_id, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        logger.debug("archive llm call skipped", exc_info=True)


def _writer_loop(q: queue.Queue[tuple[str, str]]) -> None:
    buffers: dict[Path, list[str]] = {}
    last_flush = time.monotonic()
    last_sweep = time.monotonic()
    while True:
        try:
            session_id, line = q.get(timeout=0.5)
        except queue.Empty:
            session_id, line = "", ""
        except Exception:  # noqa: BLE001
            continue

        if session_id:
            path = ARCHIVE_ROOT / _safe_segment(session_id) / f"{_shard_name()}.jsonl"
            buffers.setdefault(path, []).append(line)

        now = time.monotonic()
        pending = sum(len(v) for v in buffers.values())
        if pending and (now - last_flush >= _FLUSH_INTERVAL_SECONDS or pending >= _FLUSH_MAX_LINES):
            _flush(buffers)
            last_flush = now
        if now - last_sweep >= _SWEEP_INTERVAL_SECONDS:
            _sweep_expired()
            last_sweep = now


def _flush(buffers: dict[Path, list[str]]) -> None:
    for path, lines in list(buffers.items()):
        if not lines:
            buffers.pop(path, None)
            continue
        chunk = "".join(line + "\n" for line in lines)
        buffers[path] = []
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(chunk)
        except Exception:  # noqa: BLE001 - 单分片写失败不得中断写线程
            logger.debug("archive flush failed path=%s", path, exc_info=True)


def _sweep_expired() -> None:
    """按保留期回收过期分片（0 天表示永久保留）。"""
    try:
        retention_days = int(get_config().archive.retention_days)
    except Exception:  # noqa: BLE001
        return
    if retention_days <= 0 or not ARCHIVE_ROOT.exists():
        return
    cutoff = time.time() - retention_days * 86400
    try:
        for session_dir in ARCHIVE_ROOT.iterdir():
            if not session_dir.is_dir():
                continue
            for shard in session_dir.glob("*.jsonl"):
                try:
                    if shard.stat().st_mtime < cutoff:
                        shard.unlink()
                except OSError:
                    continue
            try:
                if not any(session_dir.iterdir()):
                    session_dir.rmdir()
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        logger.debug("archive sweep failed", exc_info=True)


__all__ = ["ARCHIVE_ROOT", "archive_event", "archive_llm_call"]
