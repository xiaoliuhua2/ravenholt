"""把 ravenholt 的漏洞报告（ReportState）镜像进 ravenholt 的 WorkProject。

红线约束「证据唯一来源」：ravenholt 报告是 agent 自述，**不含可重放 evidence**，因此
镜像进来的 finding 一律落 ``suspected``（草稿），绝不允许直接 ``validated``；只有经
ravenholt 独立验证器重放复现（关联 ``evidence_id``）后才可能升级状态，且该升级由
``service.evidence.gate`` 强制把关（见 ``service/work_project/findings.py``）。

镜像采用「同步收集 + 运行结束统一落库」：ravenholt 的 ``vulnerability_found_callback`` 是
同步回调，异步落库不能在回调里安全创建，故先入队，run 结束后由 ``flush`` 统一写库。
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

from schema.work_project.findings import (
    WorkProjectFindingRequest,
    WorkProjectFindingSeverity,
    WorkProjectFindingStatus,
)


logger = logging.getLogger(__name__)

SEVERITY_MAP: dict[str, WorkProjectFindingSeverity] = {
    "critical": WorkProjectFindingSeverity.CRITICAL,
    "high": WorkProjectFindingSeverity.HIGH,
    "medium": WorkProjectFindingSeverity.MEDIUM,
    "low": WorkProjectFindingSeverity.LOW,
    "info": WorkProjectFindingSeverity.INFO,
    "informational": WorkProjectFindingSeverity.INFO,
}

_MAX_TEXT_CHARS = 30000

_SEVERITY_LABEL: dict[WorkProjectFindingSeverity, str] = {
    WorkProjectFindingSeverity.CRITICAL: "严重",
    WorkProjectFindingSeverity.HIGH: "高危",
    WorkProjectFindingSeverity.MEDIUM: "中危",
    WorkProjectFindingSeverity.LOW: "低危",
    WorkProjectFindingSeverity.INFO: "信息",
}

# 「匿名」判定：打通那一枪没有登录态（见 src-hunt 匿名闸）。
_ANONYMOUS_PATTERN = re.compile(r"未认证|匿名|未登录")

_MISSING_SECTION = "*（本报告未提供该段内容）*"


def _cell(value: str) -> str:
    """Markdown 表格单元格：转义竖线、压平换行，空值占位。"""
    flat = (value or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()
    return flat or "—"


def _first_sentence(text: str) -> str:
    """表格单元格用的一句话：优先取第一条列表项的正文，跳过「逐条取了一遍，结果如下」这类导语。"""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    lead = ""
    for line in lines:
        matched = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if matched:
            lead = matched.group(1)
            break
    if not lead:
        lead = " ".join(lines)
    if not lead:
        return ""
    match = re.search(r"[。！？\n]", lead)
    sentence = lead[: match.end()] if match else lead
    # 危害面是表格单元格，过长会把表格撑变形；超长按句截断。
    return sentence if len(sentence) <= 200 else sentence[:197].rstrip("，、；,; ") + "…"


def _spec_section(title: str, body: str) -> list[str]:
    """规范版的一段：`## 标题` + 正文 + 段间 `---`。"""
    return [f"## {title}", "", body.strip() or _MISSING_SECTION, "", "---", ""]


_MAX_CODE_LOCATIONS = 5
_MAX_SNIPPET_CHARS = 1200


def _code_location_section(report: dict[str, Any]) -> list[str]:
    """白盒报告的「代码位置」段。

    报告是 agent 自述，``code_locations`` 是它给出的文件/行号线索（不是已复现证据）；
    没有该字段时返回空列表，渗透报告因此逐字不受影响。
    """
    raw = report.get("code_locations")
    if not isinstance(raw, list):
        return []
    rows: list[str] = []
    for item in raw[:_MAX_CODE_LOCATIONS]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("file") or "").strip()
        if not path:
            continue
        start = item.get("start_line")
        end = item.get("end_line")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            span = f"L{start}-{end}"
        elif isinstance(start, int):
            span = f"L{start}"
        else:
            span = ""
        label = str(item.get("label") or "").strip()
        rows.append(f"- `{path}` {span}{f'（{label}）' if label else ''}".rstrip())
        snippet = str(item.get("snippet") or "").strip()
        if snippet:
            rows.extend(["", "```", snippet[:_MAX_SNIPPET_CHARS], "```"])
    if not rows:
        return []
    return ["## 代码位置", "", *rows, "", "---", ""]


def report_to_finding_request(
    report: dict[str, Any],
    *,
    evidence_id: int | None = None,
    asset_id: int | None = None,
) -> WorkProjectFindingRequest:
    """ravenholt 漏洞报告 dict → ``WorkProjectFindingRequest``（纯映射，不落库）。

    带可重放证据时请求 ``validated``（由 evidence gate 按实际 verdict 复核，未复现仍会
    降回 ``suspected``）；没有证据时直接按草稿提交，绝不自行宣布已验证。
    """
    severity = SEVERITY_MAP.get(
        str(report.get("severity") or "").strip().lower(),
        WorkProjectFindingSeverity.INFO,
    )
    title = str(report.get("title") or "").strip() or "Untitled finding"
    return WorkProjectFindingRequest(
        title=title[:255],
        severity=severity,
        asset_id=asset_id,
        status=(
            WorkProjectFindingStatus.VALIDATED
            if evidence_id is not None
            else WorkProjectFindingStatus.SUSPECTED
        ),
        evidence_id=evidence_id,
        description=_compose_description(report),
        impact=str(report.get("impact") or "").strip()[:_MAX_TEXT_CHARS],
    )


def _compose_description(report: dict[str, Any]) -> str:
    """把 ravenholt 报告 dict 组装成 src-hunt 规范版正文（中文 7 段）。

    格式唯一来源：src-hunt ``references/03-vuln-report-format.md``（平台技能包
    ``strix/skills/src_hunt/03-vuln-report-format.md`` 是同一份文件，md5 一致）。
    落库正文即规范版 ⇒ 报告界面原样渲染该骨架，另由证据包注入可重放整包。
    """
    title = str(report.get("title") or "").strip() or "Untitled finding"
    target = str(report.get("target") or "").strip()
    endpoint = str(report.get("endpoint") or "").strip()
    method = str(report.get("method") or "").strip()
    cve = str(report.get("cve") or "").strip()
    cwe = str(report.get("cwe") or "").strip()
    severity = SEVERITY_MAP.get(
        str(report.get("severity") or "").strip().lower(),
        WorkProjectFindingSeverity.INFO,
    )
    description = str(report.get("description") or "").strip()
    impact = str(report.get("impact") or "").strip()
    technical_analysis = str(report.get("technical_analysis") or "").strip()
    poc_description = str(report.get("poc_description") or "").strip()
    evidence = str(report.get("evidence") or "").strip()
    remediation = str(report.get("remediation_steps") or "").strip()

    source = str(report.get("id") or "").strip()
    endpoint_source = str(report.get("endpoint_source") or "").strip()
    agent = str(report.get("agent_name") or report.get("agent_id") or "").strip()
    origin = " / ".join(
        part
        for part in (
            f"ravenholt 报告 {source}" if source else "",
            f"报告代理 {agent}" if agent else "",
        )
        if part
    )
    account = "未登录（匿名）" if _ANONYMOUS_PATTERN.search(f"{title} {description}") else "—"
    interface = " ".join(part for part in (method, endpoint) if part)
    # 目标 URL 优先用「能直接打开的完整地址」：endpoint 是完整 URL 时用它，否则退回 target。
    target_url = endpoint if endpoint.lower().startswith(("http://", "https://")) else target
    # 五段只放步骤；agent 的 evidence 常混着响应原文，单独标成「证据摘录」，不混进步骤。
    reproduce = poc_description
    if evidence:
        reproduce = "\n\n".join(
            part for part in (
                reproduce,
                f"**证据摘录（agent 自述，非平台重放）**\n\n{evidence}",
            )
            if part
        )
    type_parts = " / ".join(part for part in (cve, cwe) if part)

    lines: list[str] = [
        "# 安全漏洞报告",
        "",
        "## 一、漏洞基本信息",
        "",
        "| 项 | 内容 |",
        "| --- | --- |",
        f"| 漏洞标题 | {_cell(title)} |",
        f"| 目标系统 | {_cell(target)} |",
        f"| 目标 URL | {_cell(target_url)} |",
        f"| 漏洞类型 | {_cell(type_parts)} |",
        f"| 漏洞等级 | {_cell(_SEVERITY_LABEL[severity])} |",
        f"| 危害面 | {_cell(_first_sentence(impact))} |",
        f"| 测试账号 | {account} |",
        "",
        "---",
        "",
        *_spec_section("二、漏洞概述", description),
        *_spec_section("三、影响与危害", impact),
        "## 四、涉及接口清单",
        "",
        "| 序号 | 接口 | 说明 | 来源 |",
        "| --- | --- | --- | --- |",
        f"| 1 | {_cell(interface)} | {_cell(title)} | {_cell(endpoint_source or origin)} |",
        "",
        "---",
        "",
        *_spec_section("五、复现过程", reproduce),
        *_spec_section("六、漏洞成因分析", technical_analysis),
        *_spec_section("七、修复建议", remediation),
        *_code_location_section(report),
    ]
    return "\n".join(lines).rstrip()[:_MAX_TEXT_CHARS]


def build_spec_report_markdown(report: dict[str, Any]) -> str:
    """把报告字段拼成 src-hunt 规范 7 段正文（报告路径与证据路径共用同一套骨架）。"""
    return _compose_description(report)


def _report_url(report: dict[str, Any]) -> str:
    """取报告里最能代表目标的可重放地址：请求包 URL → endpoint → target。"""
    replay = report.get("replay")
    if isinstance(replay, dict):
        url = str(replay.get("url") or "").strip()
        if url:
            return url
    for key in ("endpoint", "target"):
        value = str(report.get(key) or "").strip()
        if value:
            return value
    return ""


async def _resolve_asset_id(project_id: int, report: dict[str, Any]) -> int | None:
    """按报告目标地址在项目资产里找对应资产，供报告结构门（require_asset）使用。"""
    raw = _report_url(report)
    if not raw:
        return None
    split = urlsplit(raw if "://" in raw else f"//{raw}")
    host = (split.hostname or "").strip().lower()
    if not host:
        return None
    port = split.port
    if port is None:
        port = 443 if split.scheme == "https" else 80

    from sqlmodel import select

    from database import get_async_session
    from model.work_project.assets import WorkProjectAsset

    async with get_async_session() as session:
        rows = (
            await session.exec(
                select(WorkProjectAsset).where(
                    WorkProjectAsset.project_id == project_id,
                    WorkProjectAsset.host == host,
                )
            )
        ).all()
        if not rows:
            # 资产只登记了 URL（host 为空）时，按 identifier 里的完整主机名回退；
            # 用边界匹配，避免把 a.example.com 误配到 example.com。
            token = re.compile(rf"(?<![a-z0-9.-]){re.escape(host)}(?![a-z0-9.-])")
            rows = [
                row
                for row in (
                    await session.exec(
                        select(WorkProjectAsset).where(
                            WorkProjectAsset.project_id == project_id,
                            WorkProjectAsset.identifier.contains(host),
                        )
                    )
                ).all()
                if token.search(str(row.identifier or "").lower())
            ]
    if not rows:
        return None
    exact = [row for row in rows if row.port == port]
    if exact:
        return exact[0].id
    portless = [row for row in rows if row.port is None]
    if portless:
        return portless[0].id
    return None


async def _persist_replay(report: dict[str, Any]) -> int | None:
    """把报告附带的请求包落成 evidence 并交平台复验；返回 ``evidence_id``。

    报告里的请求包（``replay``）是唯一能让报告路径进入「已验证」的入口：没有它只能
    维持草稿。保存或复验失败时返回原 evidence id（若已保存）或 ``None``，由 gate 按
    实际 verdict 决定状态，绝不在这里自行判定「已验证」。
    """
    replay = report.get("replay")
    if not isinstance(replay, dict):
        return None
    url = str(replay.get("url") or "").strip()
    if not url:
        return None

    method = str(report.get("method") or "GET").strip().upper() or "GET"
    headers = replay.get("headers")
    request_package: dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": (
            {str(key): str(value) for key, value in headers.items()}
            if isinstance(headers, dict)
            else {}
        ),
    }
    body = replay.get("body")
    if isinstance(body, str) and body:
        request_package["body"] = body

    from service.evidence.store import save_evidence
    from service.evidence.verifier import verify_evidence

    try:
        evidence = await save_evidence(
            target=str(report.get("target") or url).strip() or url,
            method=method,
            url=url,
            request=request_package,
            baseline_status=int(replay.get("baseline_status") or 0),
            baseline_body=str(replay.get("baseline_body") or ""),
            probe_status=int(replay.get("probe_status") or 0),
            probe_body=str(replay.get("probe_body") or ""),
        )
    except Exception:  # noqa: BLE001 - 证据保存失败不允许吞掉 finding
        logger.exception("saving replay evidence for report %s failed", report.get("id"))
        return None

    try:
        run = await verify_evidence(evidence.id)
    except Exception:  # noqa: BLE001 - 复验失败仍保留证据，gate 会拒绝 validated
        logger.exception("replaying evidence %s failed", evidence.id)
        return evidence.id

    logger.info(
        "replay verdict for report %s: evidence=%s verdict=%s",
        report.get("id"),
        evidence.id,
        run.verdict,
    )
    return evidence.id


class WorkProjectFindingMirror:
    """收集 ravenholt 报告并在 run 结束后统一镜像为 WorkProject finding。"""

    def __init__(self, *, project_id: int, session_id: str, agent_code: str = "") -> None:
        self._project_id = project_id
        self._session_id = session_id
        self._agent_code = agent_code
        self._pending: list[dict[str, Any]] = []
        self.finding_ids: list[int] = []

    def on_report(self, report: dict[str, Any]) -> None:
        """ravenholt ``vulnerability_found_callback``（同步）——仅入队。"""
        if isinstance(report, dict):
            self._pending.append(dict(report))

    async def flush(self) -> list[int]:
        """把已收集的报告落库为 finding，返回新建 finding id 列表。

        报告带可重放请求包时先保存证据并交平台复验，再请求 ``validated``（gate 按
        verdict 复核）；没有请求包的报告按草稿落库。
        """
        from service.work_project.findings import create_work_project_finding

        created: list[int] = []
        while self._pending:
            report = self._pending.pop(0)
            asset_id = await _resolve_asset_id(self._project_id, report)
            evidence_id = await _persist_replay(report)
            request = report_to_finding_request(
                report, evidence_id=evidence_id, asset_id=asset_id
            )
            finding, error = await create_work_project_finding(
                self._project_id,
                request,
                created_by_agent_code=self._agent_code or str(report.get("agent_name") or ""),
                created_from_session_id=self._session_id,
            )
            if error:
                logger.warning(
                    "mirroring strix report %s to work project %s failed: %s",
                    report.get("id"),
                    self._project_id,
                    error,
                )
                continue
            if finding is not None:
                created.append(finding.id)
                self.finding_ids.append(finding.id)
        return created

    @property
    def pending_count(self) -> int:
        return len(self._pending)


__all__ = ["WorkProjectFindingMirror", "report_to_finding_request"]
