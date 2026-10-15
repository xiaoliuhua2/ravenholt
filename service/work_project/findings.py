import json
from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from database import get_async_session
from model.evidence.evidence import Evidence
from model.evidence.verifier_runs import VerifierRun
from model.work_project.assets import WorkProjectAsset
from model.work_project.findings import WorkProjectFinding
from model.work_project.graph import WorkProjectGraphEdge
from schema.work_project.evidence import WorkProjectFindingEvidenceSchema
from schema.work_project.findings import (
    WorkProjectFindingRequest,
    WorkProjectFindingSchema,
    WorkProjectFindingStatus,
)
from service.common.pagination import Page, paginate_statement
from service.evidence.gate import assert_finding_verifiable, assert_report_complete


async def query_work_project_findings(
    project_id: int,
    *,
    page: int,
    size: int,
    keyword: str,
) -> Page[WorkProjectFindingSchema]:
    statement = (
        select(WorkProjectFinding)
        .where(WorkProjectFinding.project_id == project_id)
        .order_by(WorkProjectFinding.id)
    )
    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(or_(
            WorkProjectFinding.title.ilike(pattern),
            WorkProjectFinding.description.ilike(pattern),
            WorkProjectFinding.impact.ilike(pattern),
            cast(WorkProjectFinding.severity, String).ilike(pattern),
            cast(WorkProjectFinding.status, String).ilike(pattern),
        ))
    page_result = await paginate_statement(statement, page=page, size=size)
    return Page(
        page=page_result.page,
        size=page_result.size,
        total=page_result.total,
        items=[WorkProjectFindingSchema.model_validate(item) for item in page_result.items],
    )


async def create_work_project_finding(
    project_id: int,
    request: WorkProjectFindingRequest,
    *,
    created_by_agent_code: str = "",
    created_from_session_id: str = "",
) -> tuple[WorkProjectFindingSchema | None, str]:
    now = datetime.now()
    async with get_async_session() as session:
        error = await _validate_refs(session, project_id, request)
        if error:
            return None, error
        # Evidence gate: a non-draft status is only honoured when the attached
        # evidence was independently reproduced; otherwise the status falls back
        # to draft ('suspected'). See service/evidence/gate.py.
        status = await _gated_status(request.status, request)
        finding = WorkProjectFinding(
            project_id=project_id,
            asset_id=request.asset_id,
            edge_id=request.edge_id,
            evidence_id=request.evidence_id,
            title=request.title,
            severity=request.severity,
            status=status,
            description=request.description,
            impact=request.impact,
            created_by_agent_code=created_by_agent_code.strip(),
            created_from_session_id=created_from_session_id.strip(),
            created_at=now,
            updated_at=now,
            validated_at=now if status == WorkProjectFindingStatus.VALIDATED else None,
        )
        session.add(finding)
        try:
            await session.commit()
        except IntegrityError:
            # A referenced asset or edge was deleted concurrently between validation and commit.
            await session.rollback()
            return None, "asset or graph edge not found"
        await session.refresh(finding)
    return WorkProjectFindingSchema.model_validate(finding), ""


async def update_work_project_finding(
    project_id: int,
    finding_id: int,
    request: WorkProjectFindingRequest,
) -> tuple[WorkProjectFindingSchema | None, str]:
    async with get_async_session() as session:
        finding = await session.get(WorkProjectFinding, finding_id)
        if finding is None or finding.project_id != project_id:
            return None, "finding not found"
        error = await _validate_refs(session, project_id, request)
        if error:
            return None, error
        # Evidence gate (see create_work_project_finding / service/evidence/gate.py).
        status = await _gated_status(request.status, request)
        previous_status = finding.status
        now = datetime.now()
        finding.asset_id = request.asset_id
        finding.edge_id = request.edge_id
        finding.evidence_id = request.evidence_id
        finding.title = request.title
        finding.severity = request.severity
        finding.status = status
        finding.description = request.description
        finding.impact = request.impact
        finding.updated_at = now
        if status == WorkProjectFindingStatus.VALIDATED and previous_status != WorkProjectFindingStatus.VALIDATED:
            finding.validated_at = now
        elif status != WorkProjectFindingStatus.VALIDATED:
            finding.validated_at = None
        session.add(finding)
        try:
            await session.commit()
        except IntegrityError:
            # A referenced asset or edge was deleted concurrently between validation and commit.
            await session.rollback()
            return None, "asset or graph edge not found"
        await session.refresh(finding)
    return WorkProjectFindingSchema.model_validate(finding), ""


async def delete_work_project_finding(project_id: int, finding_id: int) -> str:
    async with get_async_session() as session:
        finding = await session.get(WorkProjectFinding, finding_id)
        if finding is None or finding.project_id != project_id:
            return "finding not found"
        await session.delete(finding)
        await session.commit()
    return ""


async def get_work_project_finding_evidence(
    project_id: int,
    finding_id: int,
) -> WorkProjectFindingEvidenceSchema | None:
    """返回发现关联的可重放证据包（完整请求 + baseline/probe 响应 + 验证结论）。

    无关联证据、证据缺失、或发现不属于该项目时返回 ``None``。
    """
    async with get_async_session() as session:
        finding = await session.get(WorkProjectFinding, finding_id)
        if finding is None or finding.project_id != project_id or finding.evidence_id is None:
            return None
        evidence = await session.get(Evidence, finding.evidence_id)
        if evidence is None:
            return None
        run = (
            await session.exec(
                select(VerifierRun)
                .where(VerifierRun.evidence_id == evidence.id)
                .order_by(VerifierRun.id.desc())
                .limit(1)
            )
        ).first()

    request = _json_object(evidence.request_json)
    raw_headers = request.get("headers")
    headers = (
        {str(key): str(value) for key, value in raw_headers.items()}
        if isinstance(raw_headers, dict)
        else {}
    )
    raw_body = request.get("body")
    if raw_body is None:
        raw_body = request.get("json")
    body = raw_body if isinstance(raw_body, str) else ("" if raw_body is None else json.dumps(raw_body, ensure_ascii=False))

    return WorkProjectFindingEvidenceSchema(
        finding_id=finding.id,
        evidence_id=evidence.id,
        target=evidence.target,
        method=evidence.method,
        url=evidence.url,
        request_headers=headers,
        request_body=body,
        baseline_status=evidence.baseline_status,
        baseline_body=evidence.baseline_body or "",
        probe_status=evidence.probe_status,
        probe_body=evidence.probe_body or "",
        diff=_json_object(evidence.diff_json),
        verdict=run.verdict if run is not None else "",
        verifier_note=run.note if run is not None else "",
        captured_at=evidence.created_at.isoformat() if evidence.created_at else "",
    )


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


async def _validate_refs(session, project_id: int, request: WorkProjectFindingRequest) -> str:
    if request.asset_id is not None:
        asset = await session.get(WorkProjectAsset, request.asset_id)
        if asset is None or asset.project_id != project_id:
            return "asset not found"
    if request.edge_id is not None:
        edge = await session.get(WorkProjectGraphEdge, request.edge_id)
        if edge is None or edge.project_id != project_id:
            return "graph edge not found"
    if request.evidence_id is not None:
        evidence = await session.get(Evidence, request.evidence_id)
        if evidence is None:
            return "evidence not found"
    return ""


async def _gated_status(
    status: WorkProjectFindingStatus,
    request: WorkProjectFindingRequest,
) -> WorkProjectFindingStatus:
    """Apply BOTH gates (evidence + report structure) to a requested finding status.

    Only ``suspected`` (the draft state) may be written unconditionally. Any other
    (terminal) status is downgraded to ``suspected`` unless the attached evidence was
    independently reproduced **and** the report meets the minimum completeness
    (``policy.report_gate``). We downgrade rather than raise so the finding itself is
    still recorded; the caller compares requested vs saved status to surface the reason.
    """
    if status == WorkProjectFindingStatus.SUSPECTED:
        return status
    ok, _reason = await assert_finding_verifiable(request.evidence_id)
    if not ok:
        return WorkProjectFindingStatus.SUSPECTED
    ok, _reason = assert_report_complete(
        title=request.title,
        description=request.description,
        impact=request.impact,
        asset_id=request.asset_id,
    )
    return status if ok else WorkProjectFindingStatus.SUSPECTED


async def finding_gate_reason(request: WorkProjectFindingRequest) -> str:
    """返回未通过的第一个门的原因（证据门优先，其次报告结构门）；全部通过返回空串。"""
    ok, reason = await assert_finding_verifiable(request.evidence_id)
    if not ok:
        return reason
    ok, reason = assert_report_complete(
        title=request.title,
        description=request.description,
        impact=request.impact,
        asset_id=request.asset_id,
    )
    return reason if not ok else ""
