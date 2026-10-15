"""Security-focused web research tools (Exa or Perplexity)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit, urlunsplit

import requests
from agents import RunContextWrapper, function_tool

from strix.config import load_settings


if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are assisting a cybersecurity agent specialized in vulnerability scanning
and security assessment running on Kali Linux. When responding to search queries:

1. Prioritize cybersecurity-relevant information including:
   - Vulnerability details (CVEs, CVSS scores, impact)
   - Security tools, techniques, and methodologies
   - Exploit information and proof-of-concepts
   - Security best practices and mitigations
   - Penetration testing approaches
   - Web application security findings

2. Provide technical depth appropriate for security professionals
3. Include specific versions, configurations, and technical details when available
4. Focus on actionable intelligence for security assessment
5. Cite reliable security sources (NIST, OWASP, CVE databases, security vendors)
6. When providing commands or installation instructions, prioritize Kali Linux compatibility
   and use apt package manager or tools pre-installed in Kali
7. Be detailed and specific - avoid general answers. Always include concrete code examples,
   command-line instructions, configuration snippets, or practical implementation steps
   when applicable

Structure your response to be comprehensive yet concise, emphasizing the most critical
security implications and details."""


def _perplexity_content(api_key: str, query: str) -> str:
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "sonar-reasoning-pro",
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
    }
    with requests.post(url, headers=headers, json=payload, timeout=300) as response:
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])


_EXA_PAGE_MAX_CHARS = 20000
_EXA_MAX_CONTENT_URLS = 10
_EXA_SUMMARY_PROMPT = (
    "Summarize this page for a penetration tester. Keep concrete technical detail: "
    "affected products and exact versions, CVE and CWE identifiers, CVSS scores, "
    "exploitation preconditions, payloads or commands, and mitigations. "
    "Leave out marketing copy and navigation text."
)


def _exa_result_block(result: dict[str, Any]) -> str | None:
    result_url = str(result.get("url") or result.get("id") or "")
    if not result_url:
        return None
    title = str(result.get("title") or result_url)
    parts = [f"### {title}\n{result_url}"]
    summary = str(result.get("summary") or "").strip()
    if summary:
        parts.append(summary)
    return "\n".join(parts)


def _exa_page_block(result: dict[str, Any]) -> str | None:
    result_url = str(result.get("url") or result.get("id") or "")
    text = str(result.get("text") or "").strip()
    if not result_url or not text:
        return None
    if len(text) > _EXA_PAGE_MAX_CHARS:
        text = f"{text[:_EXA_PAGE_MAX_CHARS]}\n[truncated at {_EXA_PAGE_MAX_CHARS} characters]"
    title = str(result.get("title") or result_url)
    return f"### {title}\n{result_url}\n\n{text}"


def _exa_blocks(
    results: list[Any],
    render: Callable[[dict[str, Any]], str | None],
) -> list[str]:
    blocks: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        block = render(cast("dict[str, Any]", result))
        if block:
            blocks.append(block)
    return blocks


def _exa_post(api_key: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    with requests.post(endpoint, headers=headers, json=payload, timeout=300) as response:
        response.raise_for_status()
        body: dict[str, Any] = response.json()
    return body


def _exa_content(api_key: str, query: str, search_type: str, num_results: int) -> str:
    body = _exa_post(
        api_key,
        "https://api.exa.ai/search",
        {
            "query": query,
            "type": search_type,
            "numResults": num_results,
            "contents": {"summary": {"query": _EXA_SUMMARY_PROMPT}},
        },
    )
    blocks = _exa_blocks(body.get("results") or [], _exa_result_block)
    if not blocks:
        raise ValueError("Exa response has no results")
    return "\n\n".join(blocks)


# SearXNG 是自建聚合元搜索：无需任何 API key，返回 JSON（实例需在 settings 里开 format=json）。
def _searxng_content(base_url: str, query: str, num_results: int) -> str:
    endpoint = base_url.rstrip("/") + "/search"
    with requests.get(
        endpoint,
        params={"q": query, "format": "json", "safesearch": 0, "language": "all"},
        timeout=60,
    ) as response:
        response.raise_for_status()
        body: dict[str, Any] = response.json()

    blocks: list[str] = []
    for item in (body.get("results") or [])[: max(1, num_results)]:
        if not isinstance(item, dict):
            continue
        result_url = str(item.get("url") or "")
        if not result_url:
            continue
        title = str(item.get("title") or result_url)
        snippet = str(item.get("content") or "").strip()
        block = f"### {title}\n{result_url}"
        if snippet:
            block += f"\n{snippet}"
        blocks.append(block)
    if not blocks:
        unresponsive = body.get("unresponsive_engines") or []
        raise ValueError(f"SearXNG returned no results (unresponsive={unresponsive})")
    return "\n\n".join(blocks)


def _normalize_url(url: str) -> str:
    """Canonical form for matching: case-fold scheme and host only, drop a trailing slash."""
    parts = urlsplit(url.strip())
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, "")
    )


def _exa_page_text(api_key: str, urls: list[str]) -> tuple[str, set[str]]:
    """Fetch page text and report which of the requested URLs Exa returned."""
    body = _exa_post(api_key, "https://api.exa.ai/contents", {"urls": urls, "text": True})
    blocks: list[str] = []
    fetched: set[str] = set()
    results: list[Any] = body.get("results") or []
    for result in results:
        if not isinstance(result, dict):
            continue
        page = cast("dict[str, Any]", result)
        block = _exa_page_block(page)
        if not block:
            continue
        blocks.append(block)
        fetched.add(_normalize_url(str(page.get("url") or page.get("id") or "")))
    if not blocks:
        raise ValueError("Exa returned no page contents")
    return "\n\n".join(blocks), fetched


def _resolve_provider(  # noqa: PLR0911 - each provider/missing-key case needs its own return
    integrations: Any,
) -> tuple[str, str] | dict[str, Any]:
    """Pick the search provider and its key, or return a sanitized error dict.

    For ``searxng`` the second tuple element is the **base URL**, not a key
    (a self-hosted SearXNG needs no credentials).
    """
    provider = integrations.web_search_provider
    perplexity_key = integrations.perplexity_api_key
    exa_key = integrations.exa_api_key
    searxng_url = integrations.searxng_base_url

    if provider == "perplexity":
        if not perplexity_key:
            return _not_configured_error("PERPLEXITY_API_KEY")
        return ("perplexity", perplexity_key)
    if provider == "exa":
        if not exa_key:
            return _not_configured_error("EXA_API_KEY")
        return ("exa", exa_key)
    if provider == "searxng":
        if not searxng_url:
            return _not_configured_error("STRIX_SEARXNG_BASE_URL")
        return ("searxng", searxng_url)

    if exa_key:
        return ("exa", exa_key)
    if perplexity_key:
        return ("perplexity", perplexity_key)
    if searxng_url:
        return ("searxng", searxng_url)
    return _not_configured_error("EXA_API_KEY / PERPLEXITY_API_KEY / STRIX_SEARXNG_BASE_URL")


def _not_configured_error(missing: str) -> dict[str, Any]:
    # 注意：这是**受支持的降级起点**（调用方会转走无 key 安全数据库），
    # 属于正常状态而非异常，故用 info 级，避免在无 key 部署里刷屏 warning。
    logger.info("web_search invoked without %s configured", missing)
    return {
        "success": False,
        "error": (
            "Web search is not configured for this scan "
            f"(operator needs to set {missing}). Proceed without it"
        ),
    }


def _guarded_call[T](  # noqa: PLR0911 - each error class needs its own sanitized return
    tool: str,
    rejected_hint: str,
    fetch: Callable[[], T],
) -> T | dict[str, Any]:
    """Run a provider call and translate any failure into a sanitized error dict."""
    try:
        return fetch()
    except requests.exceptions.Timeout:
        logger.warning("%s timed out", tool)
        return {"success": False, "error": f"{tool} timed out. Try again or narrow the request"}
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        logger.exception("%s HTTP error status=%s", tool, status)
        if status is not None and 400 <= status < 500:
            return {"success": False, "error": rejected_hint}
        return {"success": False, "error": f"{tool} service is unavailable. Try again later"}
    except requests.exceptions.RequestException as exc:
        # 网络类失败（例如本机 SearXNG 容器没起）现在是**受支持的降级起点**：
        # 用一行 warning 代替整段 traceback，避免每次检索都刷栈。
        logger.warning("%s network error: %s", tool, exc)
        return {"success": False, "error": f"{tool} network error. Try again later"}
    except (KeyError, IndexError, ValueError):
        logger.exception("%s response shape unexpected", tool)
        return {"success": False, "error": f"{tool} returned an unexpected response. Try again"}
    except Exception:
        logger.exception("%s failed", tool)
        return {"success": False, "error": f"{tool} failed unexpectedly"}


def _fallback_to_security_databases(query: str) -> dict[str, Any]:
    """未配置任何 provider 时的兜底：改走**无 key** 的安全数据库（NVD/OSV/CIRCL/GitHub/Exploit-DB）。

    这样即便这家部署没有 Exa/Perplexity/SearXNG，`web_search` 也不会空手而归；
    若兜底同样无结果，则退回原始的「未配置」提示，让 agent 知道该找运维补 key。
    """
    try:
        from strix.tools.security_search.tool import collect_security_results

        payload = collect_security_results(query, limit=5)
    except Exception:  # noqa: BLE001 - 兜底失败不改变对外语义
        logger.exception("web_search security-database fallback failed")
        return _not_configured_error("EXA_API_KEY / PERPLEXITY_API_KEY / STRIX_SEARXNG_BASE_URL")

    if not payload["results"]:
        # 兜底也确实没查到：如实说明（别谎报成功），并提示运维补 provider
        return {
            "success": False,
            "provider": "security-databases",
            "error": (
                "No results from the key-free security databases "
                "(NVD / OSV / CIRCL / GitHub / Exploit-DB) for this query, and no web-search "
                "provider is configured — set EXA_API_KEY / PERPLEXITY_API_KEY / "
                "STRIX_SEARXNG_BASE_URL for general web search. "
                "Note: GitHub anonymous search is rate-limited (~10 requests/min) and may be "
                "temporarily unavailable; retry in a minute or narrow the query."
            ),
            "failures": payload["failures"],
        }

    logger.info("web_search degraded to key-free security databases (no provider configured)")
    return {
        "success": True,
        "query": query,
        "provider": "security-databases",
        "note": (
            "No web-search provider is configured, so results come from key-free security "
            "databases (NVD / OSV / CIRCL / GitHub / Exploit-DB). "
            "Configure EXA / PERPLEXITY / SearXNG for general web search."
        ),
        "content": payload["content"],
    }


def _do_search(query: str) -> dict[str, Any]:
    if not query or not query.strip():
        return {"success": False, "error": "Query cannot be empty"}

    integrations = load_settings().integrations
    resolved = _resolve_provider(integrations)
    if isinstance(resolved, dict):
        # 未配置任何 provider（Exa / Perplexity / SearXNG）：降级到无 key 的安全数据库
        return _fallback_to_security_databases(query)
    provider, api_key = resolved
    logger.info("web_search provider=%s query (len=%d): %s", provider, len(query), query[:120])

    def fetch() -> str:
        if provider == "exa":
            return _exa_content(
                api_key,
                query,
                integrations.exa_search_type,
                integrations.exa_num_results,
            )
        if provider == "searxng":
            # api_key 在此分支是 SearXNG 的 base_url（见 _resolve_provider）
            return _searxng_content(api_key, query, integrations.exa_num_results)
        return _perplexity_content(api_key, query)

    outcome = _guarded_call(
        "Web search",
        (
            "Web search rejected the query. Refine it "
            "(more specific, shorter, no unusual characters) and retry"
        ),
        fetch,
    )
    if isinstance(outcome, dict):
        # SearXNG 是本机自建实例：连不上时优雅降级到无 key 安全数据库，
        # 而不是把网络错误直接抛给 agent（部署者不必维护它的容器生命周期）。
        if provider == "searxng":
            degraded = _fallback_to_security_databases(query)
            if degraded.get("success"):
                degraded["note"] = (
                    "SearXNG was unreachable, so results came from key-free security databases. "
                    + str(degraded.get("note", ""))
                )
                return degraded
        return outcome
    return {
        "success": True,
        "query": query,
        "provider": provider,
        "content": outcome,
    }


def _do_get_contents(urls: list[str]) -> dict[str, Any]:
    cleaned = [url.strip() for url in urls if url and url.strip()]
    if not cleaned:
        return {"success": False, "error": "Provide at least one URL"}
    if len(cleaned) > _EXA_MAX_CONTENT_URLS:
        return {
            "success": False,
            "error": f"Too many URLs. Pass at most {_EXA_MAX_CONTENT_URLS} per call",
        }

    integrations = load_settings().integrations
    provider = integrations.web_search_provider
    if provider == "searxng":
        logger.warning("web_get_contents invoked with the SearXNG provider")
        return {
            "success": False,
            "error": (
                "Page fetching needs the Exa provider; the current provider is searxng. "
                "Use web_search, or fetch pages with exec_command (curl) in the sandbox"
            ),
        }
    api_key = integrations.exa_api_key
    if not api_key:
        return _not_configured_error("EXA_API_KEY")
    if provider == "perplexity":
        logger.warning("web_get_contents invoked while the provider is pinned to Perplexity")
        return {
            "success": False,
            "error": (
                "Page fetching needs the Exa provider "
                "(operator pinned STRIX_WEB_SEARCH_PROVIDER to perplexity). "
                "Use web_search instead"
            ),
        }

    logger.info("web_get_contents urls=%d", len(cleaned))
    outcome = _guarded_call(
        "Page fetch",
        "Page fetch was rejected. Check the URLs are complete, public, and correctly formed",
        lambda: _exa_page_text(api_key, cleaned),
    )
    if isinstance(outcome, dict):
        return outcome
    content, fetched = outcome
    missing = [url for url in cleaned if _normalize_url(url) not in fetched]
    result: dict[str, Any] = {
        "success": True,
        "urls": [url for url in cleaned if url not in missing],
        "provider": "exa",
        "content": content,
    }
    if missing:
        logger.warning(
            "web_get_contents returned %d of %d pages", len(cleaned) - len(missing), len(cleaned)
        )
        result["failed_urls"] = missing
        result["warning"] = (
            f"Exa returned no content for {len(missing)} of {len(cleaned)} requested URLs. "
            "Those pages are missing from the content below"
        )
    return result


@function_tool(timeout=330)
async def web_search(ctx: RunContextWrapper, query: str) -> str:
    """Real-time web search (Exa, Perplexity, or self-hosted SearXNG) — your primary research tool.

    Use it liberally for anything that's not in your training data:

    - Current CVEs, advisories, and 0-days for a specific
      service/version (``OpenSSH 9.6 RCE``, ``Jenkins 2.401.3 auth
      bypass``).
    - Latest WAF / EDR bypass techniques (``Cloudflare WAF SQLi
      bypass 2025``, ``CrowdStrike Falcon evasion``).
    - Tool documentation, flag references, payload galleries.
    - Target reconnaissance / OSINT (company tech stack, leaked
      credentials, exposed assets).
    - Cloud-provider misconfiguration patterns
      (Azure/AWS/GCP-specific attack paths).
    - Bug-bounty writeups and security research papers.
    - Compliance frameworks and CWE/CVSS guidance.
    - Picking the right Python lib / Kali tool for a job (``best 2025
      lib for JWT alg-confusion``).
    - When stuck — looking up the exact error message, ``Access
      denied`` quirks, kernel-specific local-privesc exploits.

    Be specific: include version numbers, error messages, target
    technology, and the exact problem you're stuck on. The more context
    in the query, the more actionable the answer. Vague queries get
    generic answers.

    A security-focused system prompt biases responses toward CVEs,
    exploits, Kali-compatible tooling, and concrete code/command
    examples.

    With the Exa provider you get a ranked list of results, each with a
    title, URL, and a short security-focused summary. Read the result
    you need, then call ``web_get_contents`` with its URL to pull the
    full page text when a summary is not enough. With Perplexity you get
    a single synthesized cited answer.

    **Good example queries** (each is a full sentence, names a
    version/product, and asks one concrete thing):

    - ``"Found OpenSSH 7.4 on port 22 — any known RCE or privesc for
      this exact version?"``
    - ``"Cloudflare WAF is blocking my sqlmap on a login form — what
      bypass techniques work in 2025?"``
    - ``"Target runs WordPress 5.8.3 + WooCommerce 6.1.1 — current
      RCE chains for this combo?"``
    - ``"Low-priv shell on Ubuntu 20.04 kernel 5.4.0-74-generic — what
      local privesc exploits hit this kernel?"``
    - ``"Compromised domain user on Windows Server 2019 AD — quietest
      paths to Domain Admin without tripping EDR?"``
    - ``"'Access denied' uploading a webshell to IIS 10.0 — alternate
      Windows IIS upload bypass techniques?"``
    - ``"Discovered Jenkins 2.401.3 on staging — current authn-bypass
      and RCE exploits for this version?"``
    - ``"Best 2025 Python lib for JWT algorithm-confusion + weak-secret
      cracking?"``

    Args:
        query: The search query — a full sentence with version numbers,
            target tech, and the specific question. Treat it like a
            ticket title for a senior security engineer.
    """
    result = await asyncio.to_thread(_do_search, query)
    return json.dumps(result, ensure_ascii=False, default=str)


@function_tool(timeout=330)
async def web_get_contents(ctx: RunContextWrapper, urls: list[str]) -> str:
    """Fetch the full, cleaned text of specific web pages (Exa only).

    Use this as the drill-down step after ``web_search``: when a result's
    summary is not enough, pass that result's URL here to read the whole
    page. Good for reading a full advisory, a CVE writeup,
    an exploit proof-of-concept, or vendor documentation end to end.

    Prefer ``web_search`` first to find the right pages, then fetch only
    the few URLs worth reading in full — each page can be large, so avoid
    fetching many pages you do not need.

    This tool needs the Exa provider (``EXA_API_KEY``). When the operator
    pins the provider to Perplexity, it returns an error and you should
    use ``web_search`` instead.

    Some pages block extraction. When a page returns no content, the
    result lists it under ``failed_urls`` and the ``content`` field holds
    only the pages that came back. Check ``failed_urls`` before you
    conclude that a page had nothing useful.

    Args:
        urls: The page URLs to fetch, at most 10 per call. Use complete,
            public URLs (for example the ones returned by ``web_search``).
    """
    result = await asyncio.to_thread(_do_get_contents, urls)
    return json.dumps(result, ensure_ascii=False, default=str)
