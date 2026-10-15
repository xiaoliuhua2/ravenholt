from typing import Any

from pydantic import BaseModel


class WorkProjectFindingEvidenceSchema(BaseModel):
    """一条发现所关联的可重放证据包。

    证据包里是「唯一事实来源」：完整探测请求（method / url / headers / body）、
    baseline 与 probe 两个响应，以及验证器的重放结论。报告视图据此渲染
    src-hunt 规范版「复现过程」，使报告可被第三方按原包复现。
    """

    finding_id: int
    evidence_id: int
    target: str = ""
    method: str = "GET"
    url: str = ""
    request_headers: dict[str, str] = {}
    request_body: str = ""
    baseline_status: int = 0
    baseline_body: str = ""
    probe_status: int = 0
    probe_body: str = ""
    diff: dict[str, Any] = {}
    verdict: str = ""
    verifier_note: str = ""
    captured_at: str = ""
