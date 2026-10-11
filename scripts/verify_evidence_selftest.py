"""Self-test for evidence storage + the independent verifier.

Run from the project root (so ``init_engine()`` can read ``.xuanmu/config.json``):

    .venv/bin/python scripts/verify_evidence_selftest.py      # POSIX
    .venv\\Scripts\\python.exe scripts\\verify_evidence_selftest.py   # Windows

It targets the local backend itself (``http://127.0.0.1:8000``):

* positive: probe an endpoint that does NOT exist -> the differential is real,
  so ``verify_evidence()`` must return ``reproduced``;
* negative: baseline and probe both hit ``/docs`` -> no differential, so
  ``verify_evidence()`` must return ``refuted``.

Exit code is non-zero if either verdict is unexpected.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import httpx  # noqa: E402

from config import load_config  # noqa: E402
from database import create_all_tables, init_engine  # noqa: E402
from service.evidence.store import save_evidence  # noqa: E402
from service.evidence.verifier import verify_evidence  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
DOCS_URL = f"{BASE_URL}/docs"
MISSING_URL = f"{BASE_URL}/api/__no_such_endpoint__"
TARGET = "127.0.0.1:8000"


def _print_diff(label: str, raw: str) -> None:
    try:
        diff = json.loads(raw) if raw else {}
    except ValueError:
        diff = {}
    print(
        f"  {label}: status_changed={diff.get('status_changed')} "
        f"len_abs={diff.get('len_abs')} len_ratio={diff.get('len_ratio')} "
        f"content_hash_changed={diff.get('content_hash_changed')} "
        f"bizcode_changed={diff.get('bizcode_changed')} "
        f"total_changed={diff.get('total_changed')} "
        f"verdict_hint={diff.get('verdict_hint')}"
    )


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[int, str]:
    response = await client.get(url)
    return response.status_code, response.text


async def main() -> int:
    # get_config() 返回的是模块级默认实例，必须先显式加载 .xuanmu/config.json；
    # 否则数据库用户名/密码为空，asyncpg 会回退成 OS 用户（root）导致认证失败。
    load_config()
    init_engine()
    await create_all_tables()

    async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
        base_status, base_body = await _fetch(client, DOCS_URL)
        print(f"[baseline] {DOCS_URL} -> status={base_status} len={len(base_body)}")
        if base_status != 200:
            print("!! baseline /docs did not return 200; is the backend up?")
            return 1

        # --- positive case: real differential (endpoint does not exist) ---
        probe_status, probe_body = await _fetch(client, MISSING_URL)
        print(f"[probe]    {MISSING_URL} -> status={probe_status} len={len(probe_body)}")
        positive = await save_evidence(
            target=TARGET,
            method="GET",
            url=MISSING_URL,
            request={"method": "GET", "url": MISSING_URL, "headers": {}, "body": None},
            baseline_status=base_status,
            baseline_body=base_body,
            probe_status=probe_status,
            probe_body=probe_body,
        )
        print(f"[positive] evidence_id={positive.id}")
        _print_diff("original(baseline vs probe)", positive.diff_json)
        run_pos = await verify_evidence(positive.id)
        print(f"[positive] verdict={run_pos.verdict} note={run_pos.note}")
        _print_diff("verifier(diff detail)", run_pos.diff_json)

        # --- negative case: no differential (baseline == probe == /docs) ---
        negative = await save_evidence(
            target=TARGET,
            method="GET",
            url=DOCS_URL,
            request={"method": "GET", "url": DOCS_URL, "headers": {}, "body": None},
            baseline_status=base_status,
            baseline_body=base_body,
            probe_status=base_status,
            probe_body=base_body,
        )
        print(f"[negative] evidence_id={negative.id}")
        _print_diff("original(baseline vs probe)", negative.diff_json)
        run_neg = await verify_evidence(negative.id)
        print(f"[negative] verdict={run_neg.verdict} note={run_neg.note}")
        _print_diff("verifier(diff detail)", run_neg.diff_json)

    ok = run_pos.verdict == "reproduced" and run_neg.verdict == "refuted"
    print("=" * 60)
    print(f"expected: positive=reproduced, negative=refuted -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
