"""Persistence for differential evidence."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from database import get_async_session
from model.evidence.evidence import Evidence
from service.evidence.diff import four_dim_diff


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


async def save_evidence(
    *,
    target: str,
    method: str,
    url: str,
    request: dict[str, Any] | str,
    baseline_status: int,
    baseline_body: str,
    probe_status: int,
    probe_body: str,
    diff: dict[str, Any] | None = None,
) -> Evidence:
    """Persist one evidence pack.

    ``request`` is the full probe request package (``{"method", "url",
    "headers", "body"|"json"}``) that the verifier will replay. When ``diff``
    is omitted it is computed with :func:`four_dim_diff`.
    """
    if isinstance(request, str):
        request_json = request
    else:
        request_json = dumps_json(request)

    if diff is None:
        diff = four_dim_diff(baseline_status, baseline_body, probe_status, probe_body)

    evidence = Evidence(
        target=target,
        method=method,
        url=url,
        request_json=request_json,
        baseline_status=baseline_status,
        baseline_body=baseline_body or "",
        probe_status=probe_status,
        probe_body=probe_body or "",
        diff_json=dumps_json(diff),
        created_at=datetime.now(),
    )
    async with get_async_session() as session:
        session.add(evidence)
        await session.commit()
        await session.refresh(evidence)
    return evidence


async def get_evidence(evidence_id: int) -> Evidence | None:
    async with get_async_session() as session:
        return await session.get(Evidence, evidence_id)
