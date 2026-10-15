"""Evidence gate: the single checks a finding must clear before it may leave draft.

Hard principle: an agent's narrative / memory / thoughts are NOT evidence. A
finding may only reach a terminal status (verified / rejected) when the
independent verifier has replayed its stored evidence and returned
``reproduced``. This module exposes the deterministic read side of that rule;
callers (the WorkProject finding service and the agent tool) consult it and fall
back to ``draft`` when it is not satisfied.
"""

from __future__ import annotations

from sqlmodel import select

from database import get_async_session
from model.evidence.verifier_runs import VerifierRun


async def evidence_verdict(evidence_id: int) -> str | None:
    """Return the latest verifier verdict for ``evidence_id``.

    ``None`` when the evidence has no verifier run at all. The newest run wins
    (highest id), matching the append-only ``verifier_runs`` table.
    """
    async with get_async_session() as session:
        statement = (
            select(VerifierRun)
            .where(VerifierRun.evidence_id == evidence_id)
            .order_by(VerifierRun.id.desc())
            .limit(1)
        )
        run = (await session.exec(statement)).first()
    return run.verdict if run is not None else None


async def assert_finding_verifiable(evidence_id: int | None) -> tuple[bool, str]:
    """Whether a finding may leave draft, plus the reason when it may not.

    Returns ``(True, "")`` only when ``evidence_id`` exists and its latest
    verifier verdict is ``reproduced``. Any missing evidence, missing run, or
    non-``reproduced`` verdict returns ``(False, reason)``.
    """
    if evidence_id is None:
        return False, "no evidence attached: a finding without evidence can only stay 'draft'"
    verdict = await evidence_verdict(evidence_id)
    if verdict is None:
        return False, f"evidence {evidence_id} has no verifier run yet"
    if verdict != "reproduced":
        return False, f"evidence {evidence_id} latest verdict is '{verdict}', not 'reproduced'"
    return True, ""


def assert_report_complete(
    *,
    title: str,
    description: str,
    impact: str,
    asset_id: int | None,
) -> tuple[bool, str]:
    """报告结构门：finding 离开 draft 前必须达到最小报告要素（阈值见 policy.report_gate）。

    与证据门并列：**两个门都过**，finding 才允许离开 draft。只校验现有字段的完整性；
    src-hunt 7 段里的「复现步骤 / 修复建议」尚未建模，属后续工作。
    """
    from core.policy import get_policy, policy_loaded

    if not policy_loaded():
        return True, ""

    gate = get_policy().report_gate
    if not gate.enabled:
        return True, ""

    if gate.require_asset and asset_id is None:
        return False, "report missing impact asset: attach an asset before leaving draft"
    if len(title.strip()) < gate.min_title_chars:
        return False, f"report title too short (< {gate.min_title_chars} chars)"
    if len(description.strip()) < gate.min_description_chars:
        return False, f"report description too short (< {gate.min_description_chars} chars): not reviewable"
    if gate.require_impact and not impact.strip():
        return False, "report missing impact statement"
    return True, ""
