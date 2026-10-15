"""Independent verifier: replay stored evidence from the platform side.

The verifier is a DETERMINISTIC component. It must never introduce an LLM
judgement — its only job is to re-issue the stored probe request and decide
whether the stored differential still reproduces:

* differential still present  -> ``reproduced``
* differential disappeared    -> ``refuted`` (fresh is equivalent to baseline)
* replay failed / raised      -> ``error``

A finding may only become ``verified`` when a run here returns
``reproduced``; agent narratives are never trusted.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from core.policy.enforcer import PolicyDenied, enforce
from database import get_async_session
from model.evidence.evidence import Evidence
from model.evidence.verifier_runs import VerifierRun
from service.evidence.diff import four_dim_diff
from service.evidence.store import dumps_json, get_evidence


def _load_request(evidence: Evidence) -> dict[str, Any]:
    raw = evidence.request_json or ""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _replay(evidence: Evidence) -> tuple[int, str]:
    """Re-issue the stored probe request from the platform side.

    ``trust_env=False`` keeps the platform off any system/HTTP proxy so the
    replay is a faithful, direct reproduction.
    """
    spec = _load_request(evidence)
    method = str(spec.get("method") or evidence.method or "GET").upper()
    url = spec.get("url") or evidence.url
    if not url:
        raise ValueError("evidence has no replayable url")

    # 红线策略：平台侧出网复现必须先过判定（scope / denylist / 限速 / kill switch）
    decision = await enforce("evidence.replay", str(url))
    if not decision.allowed:
        raise PolicyDenied(decision)

    headers = {str(k): str(v) for k, v in (spec.get("headers") or {}).items()}
    kwargs: dict[str, Any] = {}
    if spec.get("json") is not None:
        kwargs["json"] = spec["json"]
    elif spec.get("body") is not None:
        body = spec["body"]
        kwargs["content"] = body if isinstance(body, (str, bytes)) else dumps_json(body)

    async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
        response = await client.request(method, url, headers=headers, **kwargs)
    return response.status_code, response.text


async def _record(
    evidence_id: int,
    verdict: str,
    diff: dict[str, Any],
    note: str,
) -> VerifierRun:
    run = VerifierRun(
        evidence_id=evidence_id,
        verdict=verdict,
        diff_json=dumps_json(diff),
        note=note,
        created_at=datetime.now(),
    )
    async with get_async_session() as session:
        session.add(run)
        await session.commit()
        await session.refresh(run)
    return run


async def verify_evidence(evidence_id: int) -> VerifierRun:
    evidence = await get_evidence(evidence_id)
    if evidence is None:
        # cannot persist: evidence_id would violate the FK. Return a transient
        # run so callers still get a deterministic verdict.
        return VerifierRun(
            evidence_id=evidence_id,
            verdict="error",
            diff_json="{}",
            note="evidence not found",
            created_at=datetime.now(),
        )

    try:
        fresh_status, fresh_body = await _replay(evidence)
    except Exception as exc:  # noqa: BLE001 - any replay failure is an error verdict
        return await _record(evidence_id, "error", {}, f"replay failed: {exc}")

    # does the original baseline-vs-probe differential still exist?
    repro = four_dim_diff(
        evidence.baseline_status,
        evidence.baseline_body,
        fresh_status,
        fresh_body,
    )
    # how close is the replay to the original probe capture?
    consistency = four_dim_diff(
        evidence.probe_status,
        evidence.probe_body,
        fresh_status,
        fresh_body,
    )

    if repro["changed"]:
        verdict = "reproduced"
        note = "differential still present: baseline vs fresh differs"
    else:
        verdict = "refuted"
        note = "differential gone: fresh is equivalent to baseline"

    detail = {
        "verdict": verdict,
        "replay_status": fresh_status,
        "replay_len": len(fresh_body or ""),
        "baseline_vs_fresh": repro,
        "fresh_vs_probe": consistency,
    }
    return await _record(evidence_id, verdict, detail, note)
