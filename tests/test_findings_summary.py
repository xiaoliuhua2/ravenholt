"""收尾总结不应暴露内部实现（函数、路径、内部服务名）。"""

from __future__ import annotations

from core.strix_runtime.findings import _sanitize_public_text, render_findings_summary


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
