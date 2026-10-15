"""ravenholt 运行时的证据工具：把可重放的差分证据落库并交平台独立验证器裁决。

红线「证据唯一来源」：**agent 自述不算证据**。agent 报洞时必须经此工具提交
baseline / probe 请求响应，由平台侧**确定性**验证器重放复现；只有复现成功
（``verdict == "reproduced"``）的 finding 才可能离开草稿态（``suspected``）——
该降级由 ``service.evidence.gate`` 强制把关，本工具不自行判定。

容器/项目上下文从运行上下文的 dict 取：``work_project_id`` / ``session_id`` / ``agent_id``。
"""

from __future__ import annotations

import json
from typing import Any

from agents import RunContextWrapper, function_tool

from schema.work_project.findings import (
    WorkProjectFindingRequest,
    WorkProjectFindingSeverity,
    WorkProjectFindingStatus,
)
from core.strix_runtime.findings import SEVERITY_MAP
from service.evidence.store import save_evidence
from service.evidence.verifier import verify_evidence
from service.work_project.findings import create_work_project_finding

_MAX_BODY_CHARS = 200_000


def _inner(ctx: RunContextWrapper) -> dict[str, Any]:
    return ctx.context if isinstance(ctx.context, dict) else {}


def _json(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_headers(headers_json: str) -> dict[str, str]:
    raw = (headers_json or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


@function_tool
async def record_evidence(
    ctx: RunContextWrapper,
    title: str,
    url: str,
    method: str = "GET",
    baseline_status: int = 0,
    baseline_body: str = "",
    probe_status: int = 0,
    probe_body: str = "",
    severity: str = "info",
    description: str = "",
    impact: str = "",
    target: str = "",
    headers_json: str = "",
    body: str = "",
) -> str:
    """Record a replayable differential evidence pack; the platform verifier adjudicates it.

    Submit the baseline response (no bug) and the probe response (with the bug) for one
    request definition. The platform replays `url` itself and re-checks the four-dimension
    diff; only a reproduced differential lets the attached finding leave 'suspected'.

    Args:
        title: finding title.
        url: the request URL the platform will replay.
        method: HTTP method (default GET).
        baseline_status: status code of the baseline (control) response.
        baseline_body: body of the baseline response.
        probe_status: status code of the probe response that shows the bug.
        probe_body: body of the probe response.
        severity: info|low|medium|high|critical.
        description: what the bug is.
        impact: why it matters.
        target: logical target (host/URL prefix); defaults to `url`.
        headers_json: JSON object string of headers to send on the replay (cookies/auth included).
        body: request body to send on the replay (empty string = no body).

    Returns:
        JSON with evidence_id, verdict, finding_id, finding_status, note, or an error.
    """
    inner = _inner(ctx)
    project_id = inner.get("work_project_id")
    session_id = str(inner.get("session_id") or "")
    agent_code = str(inner.get("agent_id") or "")

    if not isinstance(project_id, int):
        return _json(ok=False, error="no work project bound: evidence cannot attach to a finding")
    if not title.strip():
        return _json(ok=False, error="title is required")
    if not url.strip():
        return _json(ok=False, error="url is required")

    request_package: dict[str, Any] = {
        "method": (method or "GET").upper().strip(),
        "url": url.strip(),
        "headers": _parse_headers(headers_json),
    }
    if body:
        request_package["body"] = body

    try:
        evidence = await save_evidence(
            target=target.strip() or url.strip(),
            method=request_package["method"],
            url=request_package["url"],
            request=request_package,
            baseline_status=int(baseline_status),
            baseline_body=(baseline_body or "")[:_MAX_BODY_CHARS],
            probe_status=int(probe_status),
            probe_body=(probe_body or "")[:_MAX_BODY_CHARS],
        )
    except Exception as exc:  # noqa: BLE001 - tool errors must be model-visible results
        return _json(ok=False, error=f"saving evidence failed: {exc}")

    try:
        run = await verify_evidence(evidence.id)
    except Exception as exc:  # noqa: BLE001
        return _json(ok=False, evidence_id=evidence.id, error=f"verification failed: {exc}")

    severity_value = SEVERITY_MAP.get(
        str(severity).strip().lower(), WorkProjectFindingSeverity.INFO
    )
    try:
        finding, error = await create_work_project_finding(
            project_id,
            WorkProjectFindingRequest(
                title=title.strip()[:255],
                severity=severity_value,
                # 请求 validated；无复现证据时由 evidence gate 降级为 suspected。
                status=WorkProjectFindingStatus.VALIDATED,
                description=description.strip(),
                impact=impact.strip(),
                evidence_id=evidence.id,
            ),
            created_by_agent_code=agent_code,
            created_from_session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _json(
            ok=False, evidence_id=evidence.id, verdict=run.verdict,
            error=f"creating finding failed: {exc}",
        )

    if error or finding is None:
        return _json(
            ok=False, evidence_id=evidence.id, verdict=run.verdict,
            error=f"creating finding failed: {error or 'unknown'}",
        )

    return _json(
        ok=True,
        evidence_id=evidence.id,
        verdict=run.verdict,
        finding_id=finding.id,
        finding_status=finding.status.value,
        note=run.note,
    )


# 挂给 ravenholt root/child 的证据工具（仅在绑定了 WorkProject 时挂载）。
EVIDENCE_TOOLS: tuple[Any, ...] = (record_evidence,)


__all__ = ["EVIDENCE_TOOLS", "record_evidence"]
