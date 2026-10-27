"""ravenholt 运行时的证据工具：把可重放的差分证据落库并交平台独立验证器裁决。

红线「证据唯一来源」：**agent 自述不算证据**。agent 报洞时必须经此工具提交
baseline / probe 请求响应，由平台侧**确定性**验证器重放复现；只有复现成功
（``verdict == "reproduced"``）的 finding 才可能离开草稿态（``suspected``）——
该降级由 ``service.evidence.gate`` 强制把关，本工具不自行判定。

报告正文与「报告路径」共用同一套 src-hunt 规范 7 段骨架（``build_spec_report_markdown``）：
证据路径同样要写技术分析、修复建议、接口来源等字段，避免出现「能重放但六、七段空白」的残缺报告。

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
from core.strix_runtime.findings import (
    SEVERITY_MAP,
    _resolve_asset_id,
    build_spec_report_markdown,
)
from service.evidence.store import save_evidence
from service.evidence.verifier import verify_evidence
from service.work_project.findings import create_work_project_finding

_MAX_BODY_CHARS = 200_000
_MIN_POC_CHARS = 20


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


async def _record_evidence(
    *,
    project_id: int,
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
    technical_analysis: str = "",
    remediation_steps: str = "",
    poc_description: str = "",
    cwe: str = "",
    cve: str = "",
    endpoint_source: str = "",
    agent_code: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """保存证据 → 平台重放 → 组装规范 7 段报告并落 finding；tool 只负责取运行上下文。"""
    if not title.strip():
        return {"ok": False, "error": "title is required"}
    if not url.strip():
        return {"ok": False, "error": "url is required"}
    if len((poc_description or "").strip()) < _MIN_POC_CHARS:
        return {
            "ok": False,
            "error": (
                "poc_description must spell out the reproduction steps "
                f"({_MIN_POC_CHARS}+ characters): the request, the payload, and the "
                "observed response — not a one-line summary"
            ),
        }
    if int(baseline_status or 0) <= 0 or int(probe_status or 0) <= 0:
        return {
            "ok": False,
            "error": (
                "baseline_status and probe_status must be positive HTTP status codes: "
                "a replayable package needs the control response and the attack response"
            ),
        }

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
        return {"ok": False, "error": f"saving evidence failed: {exc}"}

    try:
        run = await verify_evidence(evidence.id)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "evidence_id": evidence.id, "error": f"verification failed: {exc}"}

    severity_value = SEVERITY_MAP.get(
        str(severity).strip().lower(), WorkProjectFindingSeverity.INFO
    )
    description_markdown = build_spec_report_markdown({
        "title": title.strip(),
        "target": target.strip() or url.strip(),
        "endpoint": request_package["url"],
        "method": request_package["method"],
        "cve": cve.strip(),
        "cwe": cwe.strip(),
        "severity": str(severity).strip().lower(),
        "description": description.strip(),
        "impact": impact.strip(),
        "technical_analysis": technical_analysis.strip(),
        "poc_description": poc_description.strip(),
        "remediation_steps": remediation_steps.strip(),
        "endpoint_source": endpoint_source.strip(),
        "agent_name": agent_code,
    })
    try:
        asset_id = await _resolve_asset_id(
            project_id,
            {"target": target.strip() or url.strip(), "endpoint": request_package["url"]},
        )
        finding, error = await create_work_project_finding(
            project_id,
            WorkProjectFindingRequest(
                title=title.strip()[:255],
                severity=severity_value,
                # 请求 validated；无复现证据时由 evidence gate 降级为 suspected。
                status=WorkProjectFindingStatus.VALIDATED,
                description=description_markdown,
                impact=impact.strip(),
                evidence_id=evidence.id,
                asset_id=asset_id,
            ),
            created_by_agent_code=agent_code,
            created_from_session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "evidence_id": evidence.id, "verdict": run.verdict,
            "error": f"creating finding failed: {exc}",
        }

    if error or finding is None:
        return {
            "ok": False, "evidence_id": evidence.id, "verdict": run.verdict,
            "error": f"creating finding failed: {error or 'unknown'}",
        }

    return {
        "ok": True,
        "evidence_id": evidence.id,
        "verdict": run.verdict,
        "finding_id": finding.id,
        "finding_status": finding.status.value,
        "note": run.note,
    }


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
    technical_analysis: str = "",
    remediation_steps: str = "",
    poc_description: str = "",
    cwe: str = "",
    cve: str = "",
    endpoint_source: str = "",
) -> str:
    """Record a replayable differential evidence pack and write the full src-hunt report.

    Submit the baseline response (no bug) and the probe response (with the bug) for one
    request definition. The platform replays `url` itself and re-checks the four-dimension
    diff; only a reproduced differential lets the attached finding leave 'suspected'.

    The finding body is composed from the fields below into the canonical seven-section
    report (基本信息 / 概述 / 危害 / 接口清单 / 复现过程 / 成因分析 / 修复建议), so fill
    them the same way a written report would: first person, concrete leaked values in
    `impact`, full source URL in `endpoint_source`.

    Args:
        title: finding title.
        url: the request URL the platform will replay.
        method: HTTP method (default GET).
        baseline_status: status code of the baseline (control) response. Required and
            must be positive: without it there is no differential to reproduce.
        baseline_body: body of the baseline response.
        probe_status: status code of the probe response that shows the bug. Required
            and must be positive.
        probe_body: body of the probe response.
        severity: info|low|medium|high|critical.
        description: 第二段「漏洞概述」——第一人称讲我没登录 / 拿自己的会话做成了什么。
        impact: 第三段「影响与危害」——逐条写伤害并举例（邮箱、手机号、卡尾号、订单号等实值）。
        target: logical target (host/URL prefix); defaults to `url`.
        headers_json: JSON object string of headers to send on the replay (cookies/auth included).
        body: request body to send on the replay (empty string = no body).
        technical_analysis: 第六段「漏洞成因分析」——鉴权挂在哪、漏在哪、字段为何未裁剪。
        remediation_steps: 第七段「修复建议」——可落地的整改项。
        poc_description: 第五段「复现过程」的步骤叙述（只写步骤与请求，不贴回包）。
            必填且至少 20 字：写清请求、载荷与观察到的响应；一句话会被拒绝。
        cwe: CWE 编号，如 CWE-862。
        cve: CVE 编号（没有就留空）。
        endpoint_source: 第四段接口来源，如 JS bundle 的完整 URL。

    Returns:
        JSON with evidence_id, verdict, finding_id, finding_status, note, or an error.
    """
    inner = _inner(ctx)
    project_id = inner.get("work_project_id")
    if not isinstance(project_id, int):
        return _json(ok=False, error="no work project bound: evidence cannot attach to a finding")

    return _json(**await _record_evidence(
        project_id=project_id,
        title=title,
        url=url,
        method=method,
        baseline_status=baseline_status,
        baseline_body=baseline_body,
        probe_status=probe_status,
        probe_body=probe_body,
        severity=severity,
        description=description,
        impact=impact,
        target=target,
        headers_json=headers_json,
        body=body,
        technical_analysis=technical_analysis,
        remediation_steps=remediation_steps,
        poc_description=poc_description,
        cwe=cwe,
        cve=cve,
        endpoint_source=endpoint_source,
        agent_code=str(inner.get("agent_id") or ""),
        session_id=str(inner.get("session_id") or ""),
    ))


# 挂给 ravenholt root/child 的证据工具（仅在绑定了 WorkProject 时挂载）。
EVIDENCE_TOOLS: tuple[Any, ...] = (record_evidence,)


__all__ = ["EVIDENCE_TOOLS", "record_evidence"]
