"""策略写入的全局串行锁。

所有「读当前策略 → 改 → 写回文件 → 重载」的流程都必须在这把锁下进行，
否则并发写入会互相覆盖或把文件写坏。策略是单份全局配置，故用单一进程内锁。
"""

from __future__ import annotations

import asyncio


update_lock = asyncio.Lock()
