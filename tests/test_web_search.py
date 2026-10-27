"""Tests for web_search/web_get_contents provider selection and the Exa backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import requests

from strix.config.settings import IntegrationSettings
from strix.interface.environment import _missing_web_search_vars
from strix.tools.web_search import tool


if TYPE_CHECKING:
    from typing import Self


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body
        self.headers: dict[str, str] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


def test_auto_prefers_exa_when_both_keys_set() -> None:
    integrations = IntegrationSettings(PERPLEXITY_API_KEY="pk", EXA_API_KEY="ek")
    assert tool._resolve_provider(integrations) == ("exa", "ek")


def test_auto_falls_back_to_perplexity_when_only_perplexity_is_set() -> None:
    integrations = IntegrationSettings(PERPLEXITY_API_KEY="pk")
    assert tool._resolve_provider(integrations) == ("perplexity", "pk")


def test_explicit_exa_ignores_a_configured_perplexity_key() -> None:
    integrations = IntegrationSettings(
        PERPLEXITY_API_KEY="pk",
        EXA_API_KEY="ek",
        STRIX_WEB_SEARCH_PROVIDER="exa",
    )
    assert tool._resolve_provider(integrations) == ("exa", "ek")


def test_explicit_perplexity_ignores_a_configured_exa_key() -> None:
    integrations = IntegrationSettings(
        PERPLEXITY_API_KEY="pk",
        EXA_API_KEY="ek",
        STRIX_WEB_SEARCH_PROVIDER="perplexity",
    )
    assert tool._resolve_provider(integrations) == ("perplexity", "pk")


def test_explicit_exa_without_a_key_names_only_exa() -> None:
    integrations = IntegrationSettings(
        PERPLEXITY_API_KEY="pk",
        STRIX_WEB_SEARCH_PROVIDER="exa",
    )
    resolved = tool._resolve_provider(integrations)
    assert isinstance(resolved, dict)
    assert resolved["success"] is False
    assert "EXA_API_KEY" in resolved["error"]
    assert "PERPLEXITY_API_KEY" not in resolved["error"]


def test_no_keys_names_all_providers() -> None:
    resolved = tool._resolve_provider(IntegrationSettings())
    assert isinstance(resolved, dict)
    assert "EXA_API_KEY" in resolved["error"]
    assert "PERPLEXITY_API_KEY" in resolved["error"]
    assert "STRIX_SEARXNG_BASE_URL" in resolved["error"]


def test_exa_content_requests_summaries_and_renders_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "results": [
                    {
                        "url": "https://nvd.example/cve",
                        "title": "NVD entry",
                        "summary": "  CVE-2024-0001 is a heap overflow.  ",
                    },
                    {"id": "https://blog.example/post"},
                    "not-a-dict",
                    {"title": "no url"},
                ],
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    content = tool._exa_content("ek", "OpenSSH 7.4 RCE?", "auto", 5)

    assert captured["url"] == "https://api.exa.ai/search"
    assert captured["headers"]["x-api-key"] == "ek"
    assert captured["json"]["query"] == "OpenSSH 7.4 RCE?"
    assert captured["json"]["type"] == "auto"
    assert captured["json"]["numResults"] == 5
    assert captured["json"]["contents"] == {"summary": {"query": tool._EXA_SUMMARY_PROMPT}}
    assert content == (
        "### NVD entry\nhttps://nvd.example/cve\nCVE-2024-0001 is a heap overflow.\n\n"
        "### https://blog.example/post\nhttps://blog.example/post"
    )


def test_exa_content_renders_a_result_without_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_a, **_kw: _FakeResponse(
            {"results": [{"url": "https://ex.example", "title": "Ex"}]}
        ),
    )
    assert tool._exa_content("ek", "q", "auto", 5) == "### Ex\nhttps://ex.example"


@pytest.mark.parametrize("body", [{}, {"results": None}, {"results": []}, {"results": ["x"]}])
def test_exa_content_rejects_empty_results(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: _FakeResponse(body))
    with pytest.raises(ValueError, match="no results"):
        tool._exa_content("ek", "q", "auto", 5)


def test_do_search_reports_empty_exa_results_as_unexpected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: _FakeResponse({}))

    result = tool._do_search("q")

    assert result["success"] is False
    assert "unexpected response" in result["error"]


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, ["EXA_API_KEY", "PERPLEXITY_API_KEY", "STRIX_SEARXNG_BASE_URL"]),
        ({"EXA_API_KEY": "ek"}, []),
        ({"PERPLEXITY_API_KEY": "pk"}, []),
        ({"STRIX_SEARXNG_BASE_URL": "http://127.0.0.1:8888"}, []),
        ({"STRIX_WEB_SEARCH_PROVIDER": "exa", "PERPLEXITY_API_KEY": "pk"}, ["EXA_API_KEY"]),
        ({"STRIX_WEB_SEARCH_PROVIDER": "exa", "EXA_API_KEY": "ek"}, []),
        ({"STRIX_WEB_SEARCH_PROVIDER": "perplexity", "EXA_API_KEY": "ek"}, ["PERPLEXITY_API_KEY"]),
        ({"STRIX_WEB_SEARCH_PROVIDER": "perplexity", "PERPLEXITY_API_KEY": "pk"}, []),
        ({"STRIX_WEB_SEARCH_PROVIDER": "searxng"}, ["STRIX_SEARXNG_BASE_URL"]),
        (
            {"STRIX_WEB_SEARCH_PROVIDER": "searxng", "STRIX_SEARXNG_BASE_URL": "http://127.0.0.1:8888"},
            [],
        ),
    ],
)
def test_environment_validation_follows_provider_rules(
    env: dict[str, str], expected: list[str]
) -> None:
    integrations = IntegrationSettings.model_validate(env)
    assert _missing_web_search_vars(integrations) == expected


def test_exa_search_type_and_num_results_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_EXA_SEARCH_TYPE="deep-reasoning",
            STRIX_EXA_NUM_RESULTS=3,
        )

    def fake_post(_url: str, **kwargs: Any) -> _FakeResponse:
        captured["json"] = kwargs["json"]
        return _FakeResponse({"results": [{"url": "https://ex.example", "title": "Ex"}]})

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", fake_post)

    assert tool._do_search("q")["success"] is True
    assert captured["json"]["type"] == "deep-reasoning"
    assert captured["json"]["numResults"] == 3


def test_exa_page_text_requests_full_text_and_renders_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "results": [
                    {
                        "url": "https://nvd.example/cve",
                        "title": "NVD entry",
                        "text": "  Full advisory body.  ",
                    },
                    {"url": "https://empty.example", "text": "   "},
                    "not-a-dict",
                    {"text": "no url"},
                ],
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    content, fetched = tool._exa_page_text("ek", ["https://nvd.example/cve"])

    assert captured["url"] == "https://api.exa.ai/contents"
    assert captured["headers"]["x-api-key"] == "ek"
    assert captured["json"] == {"urls": ["https://nvd.example/cve"], "text": True}
    assert content == "### NVD entry\nhttps://nvd.example/cve\n\nFull advisory body."
    assert fetched == {"https://nvd.example/cve"}


def test_exa_page_text_truncates_a_long_page(monkeypatch: pytest.MonkeyPatch) -> None:
    body = "A" * (tool._PAGE_MAX_CHARS + 500)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_a, **_kw: _FakeResponse(
            {"results": [{"url": "https://ex.example", "text": body}]}
        ),
    )
    content, _fetched = tool._exa_page_text("ek", ["https://ex.example"])
    assert "truncated at" in content
    assert content.count("A") == tool._PAGE_MAX_CHARS


@pytest.mark.parametrize("body", [{}, {"results": []}, {"results": [{"url": "u"}]}])
def test_exa_page_text_rejects_pages_without_text(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: _FakeResponse(body))
    with pytest.raises(ValueError, match="no page contents"):
        tool._exa_page_text("ek", ["https://ex.example"])


@pytest.mark.parametrize("urls", [[], ["", "   "]])
def test_do_get_contents_requires_a_url(urls: list[str]) -> None:
    result = tool._do_get_contents(urls)
    assert result["success"] is False
    assert "at least one URL" in result["error"]


def test_do_get_contents_caps_the_url_count() -> None:
    urls = [f"https://ex{index}.example" for index in range(tool._EXA_MAX_CONTENT_URLS + 1)]
    result = tool._do_get_contents(urls)
    assert result["success"] is False
    assert "Too many URLs" in result["error"]


def test_do_get_contents_needs_an_exa_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(PERPLEXITY_API_KEY="pk")

    monkeypatch.setattr(tool, "load_settings", _Settings)

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is False
    assert "EXA_API_KEY" in result["error"]


def test_do_get_contents_refuses_a_perplexity_pinned_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            PERPLEXITY_API_KEY="pk",
            STRIX_WEB_SEARCH_PROVIDER="perplexity",
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is False
    assert "web_search" in result["error"]


def test_do_get_contents_returns_page_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(tool, "_exa_page_text", lambda *_a: ("page", {"https://ex.example"}))

    result = tool._do_get_contents([" https://ex.example "])

    assert result == {
        "success": True,
        "urls": ["https://ex.example"],
        "provider": "exa",
        "content": "page",
    }


def test_do_get_contents_reports_urls_exa_did_not_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_a, **_kw: _FakeResponse(
            {"results": [{"url": "https://ok.example/", "text": "Body."}]}
        ),
    )

    result = tool._do_get_contents(["https://ok.example", "https://blocked.example"])

    assert result["success"] is True
    assert result["urls"] == ["https://ok.example"]
    assert result["failed_urls"] == ["https://blocked.example"]
    assert "1 of 2" in result["warning"]
    assert "blocked.example" not in result["content"]


def test_normalize_url_folds_only_scheme_and_host() -> None:
    assert tool._normalize_url("HTTPS://Ex.Example/Path/") == tool._normalize_url(
        "https://ex.example/Path"
    )
    assert tool._normalize_url("https://ex.example/Path") != tool._normalize_url(
        "https://ex.example/path"
    )
    assert tool._normalize_url("https://ex.example/p?Q=A") != tool._normalize_url(
        "https://ex.example/p?q=a"
    )


def test_do_get_contents_omits_the_warning_when_every_page_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_a, **_kw: _FakeResponse(
            {
                "results": [
                    {"url": "https://a.example", "text": "A."},
                    {"url": "https://b.example", "text": "B."},
                ]
            }
        ),
    )

    result = tool._do_get_contents(["https://a.example", "https://b.example"])

    assert result["urls"] == ["https://a.example", "https://b.example"]
    assert "failed_urls" not in result
    assert "warning" not in result


def test_do_get_contents_sanitizes_a_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", boom)

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is False
    assert "network error" in result["error"]
    assert "ek" not in result["error"]


def test_do_search_reports_the_provider_it_used(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(tool, "_exa_content", lambda *_a: "answer")

    result = tool._do_search("OpenSSH 7.4 RCE?")

    assert result == {
        "success": True,
        "query": "OpenSSH 7.4 RCE?",
        "provider": "exa",
        "content": "answer",
    }


class _FakeHTTPErrorResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_deepseek_fetch_url_tolerates_a_trailing_v1() -> None:
    assert tool._deepseek_fetch_url(None) == "https://api.deepseek.com/v1/tools/fetch"
    assert (
        tool._deepseek_fetch_url("https://api.deepseek.com/v1")
        == "https://api.deepseek.com/v1/tools/fetch"
    )
    assert (
        tool._deepseek_fetch_url("https://proxy.internal/deepseek/")
        == "https://proxy.internal/deepseek/v1/tools/fetch"
    )


def test_do_get_contents_prefers_deepseek_when_its_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Settings:
        integrations = IntegrationSettings(DEEPSEEK_API_KEY="dk")

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse({"title": "Example Domain", "content": "  Body.  "})

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", fake_post)

    result = tool._do_get_contents([" https://ex.example "])

    assert captured["url"] == "https://api.deepseek.com/v1/tools/fetch"
    assert captured["headers"]["Authorization"] == "Bearer dk"
    assert captured["json"] == {"url": "https://ex.example"}
    assert result == {
        "success": True,
        "urls": ["https://ex.example"],
        "provider": "deepseek",
        "content": "### Example Domain\nhttps://ex.example\n\nBody.",
    }


def test_do_get_contents_honours_an_explicit_exa_pin_over_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            DEEPSEEK_API_KEY="dk",
            STRIX_WEB_SEARCH_PROVIDER="exa",
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(tool, "_exa_page_text", lambda *_a: ("page", {"https://ex.example"}))

    assert tool._do_get_contents(["https://ex.example"])["provider"] == "exa"


def test_do_get_contents_deepseek_keeps_the_pages_that_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(DEEPSEEK_API_KEY="dk")

    def fake_post(_url: str, **kwargs: Any) -> _FakeResponse:
        if kwargs["json"]["url"].endswith("blocked.example"):
            raise requests.exceptions.HTTPError(response=_FakeHTTPErrorResponse(404))
        return _FakeResponse({"title": "Ok", "content": "Body."})

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", fake_post)

    result = tool._do_get_contents(["https://ok.example", "https://blocked.example"])

    assert result["success"] is True
    assert result["urls"] == ["https://ok.example"]
    assert result["provider"] == "deepseek"
    assert result["failed_urls"] == ["https://blocked.example"]
    assert "1 of 2" in result["warning"]
    assert "blocked.example" not in result["content"]


def test_do_get_contents_deepseek_errors_when_no_page_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(DEEPSEEK_API_KEY="dk")

    def fake_post(*_args: Any, **_kwargs: Any) -> None:
        raise requests.exceptions.Timeout

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", fake_post)

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is False
    assert result["failed_urls"] == ["https://ex.example"]
    assert "no content for any requested URL" in result["error"]
    assert "dk" not in result["error"]


def test_deepseek_page_block_truncates_a_long_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # 与 Exa 分支同一口径：超长文档不能整页塞进 agent 上下文。
    body = "B" * (tool._PAGE_MAX_CHARS + 500)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *_a, **_kw: _FakeResponse({"title": "长文", "content": body}),
    )
    block = tool._deepseek_page_block("dk", None, "https://ex.example")
    assert "truncated at" in block
    assert block.count("B") == tool._PAGE_MAX_CHARS
    assert block.startswith("### 长文\nhttps://ex.example\n\n")


def test_do_get_contents_without_a_deepseek_key_keeps_the_old_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(STRIX_WEB_SEARCH_PROVIDER="searxng")

    monkeypatch.setattr(tool, "load_settings", _Settings)

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is False
    assert "searxng" in result["error"]


def test_explicit_deepseek_provider_uses_the_deepseek_key() -> None:
    integrations = IntegrationSettings(
        DEEPSEEK_API_KEY="dk",
        STRIX_WEB_SEARCH_PROVIDER="deepseek",
    )
    assert tool._resolve_provider(integrations) == ("deepseek", "dk")


def test_explicit_deepseek_without_a_key_names_only_deepseek() -> None:
    integrations = IntegrationSettings(
        EXA_API_KEY="ek",
        STRIX_WEB_SEARCH_PROVIDER="deepseek",
    )
    resolved = tool._resolve_provider(integrations)
    assert isinstance(resolved, dict)
    assert "DEEPSEEK_API_KEY" in resolved["error"]


def test_auto_never_picks_deepseek_even_when_its_key_is_set() -> None:
    # 「自动」不该替部署者选择按次计费的通道：有 searxng 就仍然走 searxng。
    integrations = IntegrationSettings(
        DEEPSEEK_API_KEY="dk",
        STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
    )
    assert tool._resolve_provider(integrations) == ("searxng", "http://127.0.0.1:8888")


def test_deepseek_content_renders_ranked_results(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return _FakeResponse(
            {
                "results": [
                    {
                        "url": "https://nvd.example/cve",
                        "title": "NVD entry",
                        "summary": "  CVE-2024-0001 is a heap overflow.  ",
                        "snippet": "short",
                    },
                    {"url": "https://blog.example/post", "snippet": "only a snippet"},
                    {"title": "no url", "summary": "x"},
                    "not-a-dict",
                ]
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    content = tool._deepseek_content("dk", None, "OpenSSH 7.4 RCE?", 5)

    assert captured["url"] == "https://api.deepseek.com/v1/tools/search"
    assert captured["headers"]["Authorization"] == "Bearer dk"
    assert captured["json"] == {"query": "OpenSSH 7.4 RCE?", "count": 5}
    assert content == (
        "### NVD entry\nhttps://nvd.example/cve\nCVE-2024-0001 is a heap overflow.\n\n"
        "### https://blog.example/post\nhttps://blog.example/post\nonly a snippet"
    )


def test_deepseek_content_clamps_the_count_to_the_api_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_post(_url: str, **kwargs: Any) -> _FakeResponse:
        captured["json"] = kwargs["json"]
        return _FakeResponse({"results": [{"url": "https://ex.example", "title": "Ex"}]})

    monkeypatch.setattr(requests, "post", fake_post)

    tool._deepseek_content("dk", None, "q", 500)

    assert captured["json"]["count"] == tool._DEEPSEEK_MAX_SEARCH_COUNT


@pytest.mark.parametrize("body", [{}, {"results": []}, {"results": ["x"]}])
def test_deepseek_content_rejects_empty_results(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> None:
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: _FakeResponse(body))
    with pytest.raises(ValueError, match="no results"):
        tool._deepseek_content("dk", None, "q", 5)


def test_do_search_reports_deepseek_as_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            DEEPSEEK_API_KEY="dk",
            STRIX_WEB_SEARCH_PROVIDER="deepseek",
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(tool, "_deepseek_content", lambda *_a: "answer")

    result = tool._do_search("OpenSSH 7.4 RCE?")

    assert result == {
        "success": True,
        "query": "OpenSSH 7.4 RCE?",
        "provider": "deepseek",
        "content": "answer",
    }


def test_deepseek_provider_requires_its_own_key_in_env_validation() -> None:
    integrations = IntegrationSettings.model_validate({"STRIX_WEB_SEARCH_PROVIDER": "deepseek"})
    assert _missing_web_search_vars(integrations) == ["DEEPSEEK_API_KEY"]


# ---------- 上游 provider 出错时的表现：提示要准、auto 要降级、钉住不降级 ----------


def _http_error(status: int) -> requests.exceptions.HTTPError:
    return requests.exceptions.HTTPError(response=_FakeHTTPErrorResponse(status))


def test_auth_failure_tells_the_operator_to_fix_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_WEB_SEARCH_PROVIDER="exa",  # 钉住 → 不降级，错误原样交给 agent
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: (_ for _ in ()).throw(_http_error(401)))

    result = tool._do_search("q")

    assert result["success"] is False
    assert result["reason"] == "auth"
    assert "API key was rejected" in result["error"]
    assert "Refine" not in result["error"]  # 不能再误导成「查询有问题」
    assert "ek" not in result["error"]


def test_quota_failure_names_the_credit_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: (_ for _ in ()).throw(_http_error(402)))
    result = tool._guarded_call("Web search", "rejected", lambda: tool._exa_content("ek", "q", "auto", 5))
    assert result["reason"] == "quota"
    assert "out of credit" in result["error"]


def test_rate_limit_failure_says_retry_later(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: (_ for _ in ()).throw(_http_error(429)))
    result = tool._guarded_call("Web search", "rejected", lambda: tool._exa_content("ek", "q", "auto", 5))
    assert result["reason"] == "rate_limit"
    assert "rate limit" in result["error"]


def test_auto_fails_over_from_a_broken_exa_to_searxng(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
        )

    def fake_post(*_args: Any, **_kwargs: Any) -> None:
        raise _http_error(401)

    def fake_get(*_args: Any, **_kwargs: Any) -> _FakeResponse:
        return _FakeResponse({"results": [{"url": "https://s.example", "title": "Searxng hit"}]})

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)

    result = tool._do_search("q")

    assert result["success"] is True
    assert result["provider"] == "searxng"
    assert "was unavailable" in result["note"]
    assert "Searxng hit" in result["content"]


def test_pinned_provider_does_not_fail_over(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
            STRIX_WEB_SEARCH_PROVIDER="exa",
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: (_ for _ in ()).throw(_http_error(401)))
    monkeypatch.setattr(requests, "get", lambda *_a, **_kw: _FakeResponse({"results": [{"url": "u"}]}))

    result = tool._do_search("q")

    assert result["success"] is False  # 钉住就得让部署者看到自己 key 的问题
    assert result["reason"] == "auth"


def test_shape_errors_do_not_fail_over(monkeypatch: pytest.MonkeyPatch) -> None:
    # 解析失败换 provider 也解决不了，静默降级只会掩盖真实故障。
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
        )

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: _FakeResponse({}))
    monkeypatch.setattr(requests, "get", lambda *_a, **_kw: _FakeResponse({"results": [{"url": "u"}]}))

    result = tool._do_search("q")

    assert result["success"] is False
    assert "unexpected response" in result["error"]


def test_auto_fails_over_to_security_databases_when_searxng_is_also_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(
            EXA_API_KEY="ek",
            STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
        )

    def dead_get(*_args: Any, **_kwargs: Any) -> None:
        raise requests.exceptions.ConnectionError

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(requests, "post", lambda *_a, **_kw: (_ for _ in ()).throw(_http_error(401)))
    monkeypatch.setattr(requests, "get", dead_get)
    monkeypatch.setattr(
        tool,
        "_fallback_to_security_databases",
        lambda query: {"success": True, "query": query, "provider": "security-databases",
                       "note": "n", "content": "db hit"},
    )

    result = tool._do_search("q")

    assert result["success"] is True
    assert result["provider"] == "security-databases"
    assert "was unavailable" in result["note"]


def test_get_contents_falls_back_to_exa_when_deepseek_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        integrations = IntegrationSettings(DEEPSEEK_API_KEY="dk", EXA_API_KEY="ek")

    monkeypatch.setattr(tool, "load_settings", _Settings)
    monkeypatch.setattr(
        tool, "_deepseek_get_contents",
        lambda *_a: {"success": False, "provider": "deepseek", "error": "out of credit"},
    )
    monkeypatch.setattr(tool, "_exa_page_text", lambda *_a: ("exa page", {"https://ex.example"}))

    result = tool._do_get_contents(["https://ex.example"])

    assert result["success"] is True
    assert result["provider"] == "exa"
    assert "fell back to Exa" in result["note"]
    assert result["content"] == "exa page"


def test_auto_prefers_searxng_over_perplexity() -> None:
    # 本机 SearXNG 免费且实测可达；Perplexity 在部分网络根本连不上，
    # 排在它前面会「一填 key 反而把检索弄废」。
    integrations = IntegrationSettings(
        PERPLEXITY_API_KEY="pk",
        STRIX_SEARXNG_BASE_URL="http://127.0.0.1:8888",
    )
    assert tool._resolve_provider(integrations) == ("searxng", "http://127.0.0.1:8888")
