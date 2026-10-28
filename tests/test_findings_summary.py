"""收尾总结不应暴露内部实现（函数、路径、内部服务名）。"""

from __future__ import annotations

from core.strix_runtime.findings import (
    WorkProjectFindingMirror,
    _sanitize_public_text,
    render_findings_summary,
)


def test_sanitize_hides_internal_implementation() -> None:
    text = (
        "单次读取上限约 4000 字符（read_text()[:4000]），"
        "路径 /home/kali/.ssh/id_rsa 未触碰；服务为 uvicorn+Ravenholt SPA"
    )
    cleaned = _sanitize_public_text(text)

    for token in ("read_text", "[:4000]", "/home/kali", "uvicorn", "Ravenholt", "SPA"):
        assert token not in cleaned
    assert "4000 字符" in cleaned
    assert "内部路径已隐去" in cleaned


def test_render_summary_sanitizes_follow_up_reason() -> None:
    markdown = render_findings_summary(
        {"total": 0, "verified": [], "suspected": [], "unverifiable": []},
        [
            {
                "surface": "http://target:8080",
                "risk_area": "路径穿越",
                "evidence": "用 read_text() 读取 /tmp/target.py；服务为 Ravenholt",
            }
        ],
    )

    assert "read_text" not in markdown
    assert "/tmp/target.py" not in markdown
    assert "Ravenholt" not in markdown
    assert "内部路径已隐去" in markdown
    assert "needs_follow_up" not in markdown
    assert "尚未完成验证的测试面" in markdown


def test_render_summary_hides_coverage_status_codes() -> None:
    markdown = render_findings_summary(
        {
            "total": 1,
            "verified": [{"title": "越权读取用户档案", "severity": "high"}],
            "suspected": [],
            "unverifiable": [],
        },
        [
            {
                "surface": "上传接口",
                "risk_area": "文件上传",
                "evidence": "needs_follow_up：PASS 部分完成，FAIL 未测，DEGRADED",
            }
        ],
    )

    for token in ("needs_follow_up", "PASS", "FAIL", "DEGRADED"):
        assert token not in markdown
    assert "待补测" in markdown
    assert "尚未完成验证的测试面" in markdown
    assert "另有 **1** 个测试面尚未完成验证，需补测或人工确认。" in markdown


def test_summary_hides_generic_english_finding_word() -> None:
    markdown = render_findings_summary(
        {
            "total": 1,
            "verified": [{"title": "未授权访问 finding /admin/config", "severity": "high"}],
            "suspected": [],
            "unverifiable": [],
        }
    )

    assert "finding" not in markdown.lower()
    assert "发现" in markdown
    assert "全部发现" in markdown


def test_mirror_drops_withdrawn_report_before_flush() -> None:
    mirror = WorkProjectFindingMirror(project_id=1, session_id="s")
    mirror.on_report({"id": "vuln-0001", "title": "临时报告"})
    mirror.on_report({"id": "vuln-0002", "title": "保留报告"})

    mirror.on_delete({"id": "vuln-0001", "title": "临时报告"})

    assert mirror.pending_count == 1
    assert mirror._pending[0]["id"] == "vuln-0002"
    assert mirror._withdrawn == ["vuln-0001"]
