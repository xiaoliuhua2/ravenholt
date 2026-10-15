"""Self-test for the finding evidence gate.

Run from the project root (so ``load_config()`` can read ``.ravenholt/config.json``):

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
from core.policy import load_policy  # noqa: E402
from database import create_all_tables, get_async_session, init_engine  # noqa: E402
from service.work_project.findings import finding_gate_reason  # noqa: E402
from model.work_project.assets import WorkProjectAsset  # noqa: E402
from model.work_project.projects import WorkProject  # noqa: E402
from schema.work_project.assets import (  # noqa: E402
    WorkProjectAssetOrigin,
    WorkProjectAssetRequest,
    WorkProjectAssetType,
)
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


async def _create_asset(project_id: int) -> int:
    """报告结构门要求绑定影响资产，所以自测也要建一个真实资产。"""
    request = WorkProjectAssetRequest(
        type=WorkProjectAssetType.SERVICE, host="127.0.0.1", port=8000
    )
    async with get_async_session() as session:
        asset = WorkProjectAsset(
            project_id=project_id,
            type=request.type,
            origin=WorkProjectAssetOrigin.DISCOVERED,
            identifier=request.identifier,
            host=request.host,
            port=request.port,
            path=request.path,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
    return asset.id


async def _create_validated_finding(
    project_id: int,
    title: str,
    evidence_id: int | None,
    *,
    asset_id: int | None = None,
    complete: bool = True,
) -> tuple[WorkProjectFindingStatus | None, str]:
    if complete:
        request = WorkProjectFindingRequest(
            title=f"{title} · 越权读取他人订单",
            severity="high",
            status=WorkProjectFindingStatus.VALIDATED,
            evidence_id=evidence_id,
            asset_id=asset_id,
            description=(
                "替换订单号即可读取其他用户的订单详情，返回体包含手机号、收货地址与订单金额；"
                "基线请求返回 200 且为本人订单，探针请求同样返回 200 但内容属于他人，"
                "差分在连续三次重放中稳定复现；将订单号递减一位即可遍历他人订单，"
                "影响面覆盖同租户全部用户，可直接用于复现、定级与报告。"
            ),
            impact="同一租户下任意用户可越权读取他人订单与 PII，属高危信息泄露。",
        )
    else:
        request = WorkProjectFindingRequest(
            title=f"{title} · 薄报告",
            severity="high",
            status=WorkProjectFindingStatus.VALIDATED,
            evidence_id=evidence_id,
            asset_id=asset_id,
            description="太短",
            impact="",
        )
    saved, error = await create_work_project_finding(project_id, request)
    if error or saved is None:
        return None, error or "no finding returned"
    if saved.status != request.status:
        reason = await finding_gate_reason(request)
        print(f"    [debug] 被降级原因: {reason}")
        print(
            f"    [debug] title={len(request.title.strip())}字 "
            f"description={len(request.description.strip())}字 "
            f"impact={bool(request.impact.strip())} asset_id={request.asset_id}"
        )
    return saved.status, ""


async def main() -> int:
    # get_config() 返回模块级默认实例，必须先显式加载 .ravenholt/config.json；
    # 否则数据库用户名/密码为空，asyncpg 回退成 OS 用户导致认证失败。
    load_config()
    # 与应用启动流程保持一致：红线策略未加载时出网判定会 fail-closed 拒绝
    load_policy()
    init_engine()
    await create_all_tables()

    project_id = await _create_project()
    asset_id = await _create_asset(project_id)
    print(f"[setup] project_id={project_id} asset_id={asset_id}")

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

    # 1) reproduced evidence + 完整报告 -> terminal status honoured（两个门都过）
    s1, err1 = await _create_validated_finding(
        project_id, "gate-pass", reproduced_ev.id, asset_id=asset_id, complete=True
    )
    print(f"[case1] reproduced + 完整报告 + validated -> status={s1} error='{err1}'")
    checks.append(("case1 reproduced + complete report passes both gates",
                   err1 == "" and s1 == WorkProjectFindingStatus.VALIDATED))

    # 2) no evidence -> downgraded to suspected (draft)
    s2, err2 = await _create_validated_finding(
        project_id, "gate-no-evidence", None, asset_id=asset_id, complete=True
    )
    print(f"[case2] no evidence + validated -> status={s2} error='{err2}'")
    checks.append(("case2 missing evidence downgrades to suspected",
                   err2 == "" and s2 == WorkProjectFindingStatus.SUSPECTED))

    # 3) evidence exists but was refuted -> downgraded to suspected (draft)
    s3, err3 = await _create_validated_finding(
        project_id, "gate-refuted", refuted_ev.id, asset_id=asset_id, complete=True
    )
    print(f"[case3] refuted + validated -> status={s3} error='{err3}'")
    checks.append(("case3 non-reproduced evidence downgrades to suspected",
                   err3 == "" and s3 == WorkProjectFindingStatus.SUSPECTED))

    # 4) reproduced evidence 但报告太薄 -> 报告结构门降级
    s4, err4 = await _create_validated_finding(
        project_id, "gate-thin-report", reproduced_ev.id, asset_id=asset_id, complete=False
    )
    print(f"[case4] reproduced + 薄报告 + validated -> status={s4} error='{err4}'")
    checks.append(("case4 reproduced but thin report is blocked by report gate",
                   err4 == "" and s4 == WorkProjectFindingStatus.SUSPECTED))

    print("=" * 60)
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"gate self-test -> {'PASS' if not failed else 'FAIL'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
