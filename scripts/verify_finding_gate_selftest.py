"""Self-test for the finding evidence gate.

Run from the project root (so ``load_config()`` can read ``.xuanmu/config.json``):

    .venv/bin/python scripts/verify_finding_gate_selftest.py              # POSIX
    .venv\\Scripts\\python.exe scripts\\verify_finding_gate_selftest.py   # Windows

It targets the local backend itself (``http://127.0.0.1:8000``) and reuses the
evidence self-test recipe to obtain a genuinely ``reproduced`` evidence pack:

* positive: probe an endpoint that does NOT exist  -> differential reproduces ->
  ``verify_evidence()`` returns ``reproduced``;
* negative: baseline and probe both hit ``/docs``  -> no differential ->
  ``verify_evidence()`` returns ``refuted``.

Then it exercises the gate through ``create_work_project_finding``:

1. reproduced evidence + status=validated -> status is honoured (validated);
2. no evidence + status=validated         -> downgraded to suspected;
3. refuted evidence + status=validated    -> downgraded to suspected.

Exit code is non-zero if any expectation fails.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import httpx  # noqa: E402

from config import load_config  # noqa: E402
from database import create_all_tables, get_async_session, init_engine  # noqa: E402
from model.work_project.projects import WorkProject  # noqa: E402
from schema.work_project.findings import (  # noqa: E402
    WorkProjectFindingRequest,
    WorkProjectFindingStatus,
)
from service.evidence.store import save_evidence  # noqa: E402
from service.evidence.verifier import verify_evidence  # noqa: E402
from service.work_project.findings import create_work_project_finding  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
DOCS_URL = f"{BASE_URL}/docs"
MISSING_URL = f"{BASE_URL}/api/__no_such_endpoint__"
TARGET = "127.0.0.1:8000"


async def _create_project() -> int:
    async with get_async_session() as session:
        project = WorkProject(name="finding-gate-selftest")
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return project.id


async def _create_validated_finding(
    project_id: int,
    title: str,
    evidence_id: int | None,
) -> tuple[WorkProjectFindingStatus | None, str]:
    request = WorkProjectFindingRequest(
        title=title,
        severity="high",
        status=WorkProjectFindingStatus.VALIDATED,
        evidence_id=evidence_id,
        description="gate self-test finding",
    )
    saved, error = await create_work_project_finding(project_id, request)
    if error or saved is None:
        return None, error or "no finding returned"
    return saved.status, ""


async def main() -> int:
    # get_config() 返回模块级默认实例，必须先显式加载 .xuanmu/config.json；
    # 否则数据库用户名/密码为空，asyncpg 回退成 OS 用户导致认证失败。
    load_config()
    init_engine()
    await create_all_tables()

    project_id = await _create_project()
    print(f"[setup] project_id={project_id}")

    checks: list[tuple[str, bool]] = []

    async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
        base_resp = await client.get(DOCS_URL)
        base_status, base_body = base_resp.status_code, base_resp.text
        print(f"[baseline] {DOCS_URL} -> status={base_status} len={len(base_body)}")
        if base_status != 200:
            print("!! baseline /docs did not return 200; is the backend up?")
            return 1

        probe_resp = await client.get(MISSING_URL)
        probe_status, probe_body = probe_resp.status_code, probe_resp.text
        print(f"[probe]    {MISSING_URL} -> status={probe_status} len={len(probe_body)}")

    # --- real evidence whose differential reproduces ---
    reproduced_ev = await save_evidence(
        target=TARGET,
        method="GET",
        url=MISSING_URL,
        request={"method": "GET", "url": MISSING_URL, "headers": {}, "body": None},
        baseline_status=base_status,
        baseline_body=base_body,
        probe_status=probe_status,
        probe_body=probe_body,
    )
    run_pos = await verify_evidence(reproduced_ev.id)
    print(f"[evidence] reproduced evidence_id={reproduced_ev.id} verdict={run_pos.verdict}")

    # --- evidence with NO differential (refuted) ---
    refuted_ev = await save_evidence(
        target=TARGET,
        method="GET",
        url=DOCS_URL,
        request={"method": "GET", "url": DOCS_URL, "headers": {}, "body": None},
        baseline_status=base_status,
        baseline_body=base_body,
        probe_status=base_status,
        probe_body=base_body,
    )
    run_neg = await verify_evidence(refuted_ev.id)
    print(f"[evidence] refuted    evidence_id={refuted_ev.id} verdict={run_neg.verdict}")

    if run_pos.verdict != "reproduced":
        print("!! expected the positive evidence to reproduce; cannot test the gate")
        return 1

    # 1) reproduced evidence -> terminal status honoured
    s1, err1 = await _create_validated_finding(project_id, "gate-pass", reproduced_ev.id)
    print(f"[case1] reproduced + validated -> status={s1} error='{err1}'")
    checks.append(("case1 reproduced evidence passes the gate",
                   err1 == "" and s1 == WorkProjectFindingStatus.VALIDATED))

    # 2) no evidence -> downgraded to suspected (draft)
    s2, err2 = await _create_validated_finding(project_id, "gate-no-evidence", None)
    print(f"[case2] no evidence + validated -> status={s2} error='{err2}'")
    checks.append(("case2 missing evidence downgrades to suspected",
                   err2 == "" and s2 == WorkProjectFindingStatus.SUSPECTED))

    # 3) evidence exists but was refuted -> downgraded to suspected (draft)
    s3, err3 = await _create_validated_finding(project_id, "gate-refuted", refuted_ev.id)
    print(f"[case3] refuted + validated -> status={s3} error='{err3}'")
    checks.append(("case3 non-reproduced evidence downgrades to suspected",
                   err3 == "" and s3 == WorkProjectFindingStatus.SUSPECTED))

    print("=" * 60)
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"gate self-test -> {'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
