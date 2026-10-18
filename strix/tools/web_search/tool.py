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


# 单页正文上限：Exa 与 DeepSeek 两条抓取路径共用同一口径，
# 免得超长文档把整页塞进 agent 上下文白烧 LLM token。
_PAGE_MAX_CHARS = 20000
_EXA_MAX_CONTENT_URLS = 10
_EXA_SUMMARY_PROMPT = (
    "Summarize this page for a penetration tester. Keep concrete technical detail: "
    "affected products and exact versions, CVE and CWE identifiers, CVSS scores, "
    "exploitation preconditions, payloads or commands, and mitigations. "
    "Leave out marketing copy and navigation text."
)

# 「换一家 provider 也许能成」的失败类型：只有这些才触发自动降级。
# 注意 shape / unknown 不在其中 —— 那是解析或我们自己的问题，换 provider 解决不了，
# 而且静默降级会把真实故障掩盖掉。
_FAILOVER_REASONS = frozenset({"auth", "quota", "rate_limit", "network", "timeout", "server"})

# DeepSeek 官方 Search/Fetch 工具接口（复用 DeepSeek API key）。
# 文档：https://api-docs.deepseek.com/zh-cn/guides/search
_DEEPSEEK_DEFAULT_BASE = "https://api.deepseek.com"
_DEEPSEEK_FETCH_TIMEOUT = 60
_DEEPSEEK_SEARCH_TIMEOUT = 60
# Search 接口 count 上限 50（官方文档：1~50）
_DEEPSEEK_MAX_SEARCH_COUNT = 50


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
    if len(text) > _PAGE_MAX_CHARS:
        text = f"{text[:_PAGE_MAX_CHARS]}\n[truncated at {_PAGE_MAX_CHARS} characters]"
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
    deepseek_key = (getattr(integrations, "deepseek_api_key", None) or "").strip()

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
    if provider == "deepseek":
        # 显式选 DeepSeek 检索：复用 DeepSeek 密钥（fetch 与 search 同一把 key）。
        if not deepseek_key:
            return _not_configured_error("DEEPSEEK_API_KEY")
        return ("deepseek", deepseek_key)

    # provider=auto：**不把 DeepSeek 放进自动链路**——检索走它会产生按次计费，
    # 要花钱的通道应由部署者显式选择，而不是自动替他们决定。
    # 顺序按「可用性优先」：Exa（唯一带摘要的付费源）→ 本机 SearXNG（免费、实测可达）
    # → Perplexity（chat 型，部分网络根本连不上；排在本地实例之后，避免一填就废掉检索）。
    if exa_key:
        return ("exa", exa_key)
    if searxng_url:
        return ("searxng", searxng_url)
    if perplexity_key:
        return ("perplexity", perplexity_key)
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
    """Run a provider call and translate any failure into a sanitized error dict.

    每个失败都带机器可读的 ``reason``，供调用方判断「换一家 provider 也许能成」
    （见 ``_FAILOVER_REASONS``）。**4xx 不打栈**——密钥 / 额度 / 限流属于运维配置问题，
    一行 warning 已足够定位，刷整段 traceback 只会淹没有用信息。
    """
    try:
        return fetch()
    except requests.exceptions.Timeout:
        logger.warning("%s timed out", tool)
        return {
            "success": False,
            "reason": "timeout",
            "error": f"{tool} timed out. Try again or narrow the request",
        }
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        reason = _http_failure_reason(status)
        logger.warning("%s HTTP error status=%s reason=%s", tool, status, reason)
        return {
            "success": False,
            "reason": reason,
            "error": _http_failure_message(tool, status, rejected_hint),
        }
    except requests.exceptions.RequestException as exc:
        # 网络类失败（例如本机 SearXNG 容器没起）现在是**受支持的降级起点**：
        # 用一行 warning 代替整段 traceback，避免每次检索都刷栈。
        logger.warning("%s network error: %s", tool, exc)
        return {
            "success": False,
            "reason": "network",
            "error": f"{tool} network error. Try again later",
        }
    except (KeyError, IndexError, ValueError):
        logger.exception("%s response shape unexpected", tool)
        return {
            "success": False,
            "reason": "shape",
            "error": f"{tool} returned an unexpected response. Try again",
        }
    except Exception:
        logger.exception("%s failed", tool)
        return {"success": False, "reason": "unknown", "error": f"{tool} failed unexpectedly"}


def _http_failure_reason(status: int | None) -> str:
    """把 HTTP 状态码归类成机器可读原因（降级判据用）。"""
    if status in (401, 403):
        return "auth"
    if status == 402:
        return "quota"
    if status == 429:
        return "rate_limit"
    if status is not None and 400 <= status < 500:
        return "rejected"
    return "server"


def _http_failure_message(tool: str, status: int | None, rejected_hint: str) -> str:
    """按状态码给「照着就能改」的提示。

    密钥无效(401/403)、余额不足(402)、限流(429) 与「查询本身有问题」是**两回事**，
    不能再统一回一句「精炼你的查询语句」——那会把运维和 agent 一起带偏。
    """
    if status in (401, 403):
        return (
            f"{tool} API key was rejected (HTTP {status}). "
            "Update the key in the console, or switch to another web-search provider"
        )
    if status == 402:
        return (
            f"{tool} account is out of credit (HTTP {status}). "
            "Top up the account, or switch to another web-search provider"
        )
    if status == 429:
        return f"{tool} hit a rate limit (HTTP {status}). Retry later, or narrow the request"
    if status is not None and 400 <= status < 500:
        return rejected_hint
    return f"{tool} service is unavailable. Try again later"


def _provider_is_pinned(integrations: Any) -> bool:
    """provider 是否被**显式钉住**（非 auto）。

    钉住时不做自动降级：尊重部署者的选择，也让他们立刻看到自己那把 key 的真实问题，
    而不是被一次静默降级掩盖过去。
    """
    return str(getattr(integrations, "web_search_provider", "auto") or "auto") != "auto"


def _should_failover(provider: str, integrations: Any, outcome: dict[str, Any]) -> bool:
    """这次失败值不值得自动换一家 provider？（只对 auto 模式、且失败属「换家能成」那类）"""
    if provider in ("searxng", "deepseek"):
        # searxng 有自己的降级分支；deepseek 只会因显式选择而出现（等同钉住）。
        return False
    return outcome.get("reason") in _FAILOVER_REASONS and not _provider_is_pinned(integrations)


def _failover_search(
    provider: str,
    integrations: Any,
    query: str,
    outcome: dict[str, Any],
) -> dict[str, Any] | None:
    """auto 模式下上游 provider 失败 → 先回落本机 SearXNG，再退无 key 安全库。

    返回 ``None`` 表示两条退路都没成，调用方应把**原始错误**交给 agent（别掩盖真实故障）。
    """
    searxng_url = str(getattr(integrations, "searxng_base_url", "") or "").strip()
    if searxng_url:
        try:
            content = _searxng_content(searxng_url, query, integrations.exa_num_results)
        except Exception:  # noqa: BLE001 - 这一层降级失败就继续走下一层
            logger.warning("web_search failover to searxng failed")
        else:
            logger.info("web_search failed over from %s to searxng", provider)
            return {
                "success": True,
                "query": query,
                "provider": "searxng",
                "note": (
                    f"{provider} was unavailable ({(outcome.get('error') or '')[:120]}). "
                    "Results come from the local SearXNG instance instead."
                ),
                "content": content,
            }

    degraded = _fallback_to_security_databases(query)
    if degraded.get("success"):
        degraded["note"] = (
            f"{provider} was unavailable, so results came from key-free security databases. "
            + str(degraded.get("note", ""))
        )
        return degraded
    return None


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
        if provider == "deepseek":
            # api_key 在此分支是 DeepSeek 密钥；base_url 走 integrations 配置
            return _deepseek_content(
                api_key,
                getattr(integrations, "deepseek_base_url", None),
                query,
                integrations.exa_num_results,
            )
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
        elif _should_failover(provider, integrations, outcome):
            # auto 模式下 Exa / Perplexity 挂了（密钥失效、额度耗尽、限流、网络不通）
            # → 换成本机 SearXNG，再不行退安全数据库；钉住 provider 时不降级。
            failed_over = _failover_search(provider, integrations, query, outcome)
            if failed_over is not None:
                return failed_over
        return outcome
    return {
        "success": True,
        "query": query,
        "provider": provider,
        "content": outcome,
    }


def _deepseek_tools_url(base_url: str | None, tool_name: str) -> str:
    """DeepSeek 官方工具接口地址（容忍 base URL 末尾带 ``/v1``）。"""
    base = (base_url or _DEEPSEEK_DEFAULT_BASE).strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    return f"{base}/v1/tools/{tool_name}"


def _deepseek_fetch_url(base_url: str | None) -> str:
    return _deepseek_tools_url(base_url, "fetch")


def _deepseek_search_url(base_url: str | None) -> str:
    return _deepseek_tools_url(base_url, "search")


def _deepseek_post(api_key: str, url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    with requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        return cast("dict[str, Any]", response.json())


def _deepseek_result_block(result: dict[str, Any]) -> str | None:
    """DeepSeek 检索结果 → 与 Exa 分支同形的块（优先用给模型读的长摘要）。"""
    result_url = str(result.get("url") or "").strip()
    if not result_url:
        return None
    title = str(result.get("title") or "").strip() or result_url
    summary = str(result.get("summary") or "").strip() or str(result.get("snippet") or "").strip()
    parts = [f"### {title}\n{result_url}"]
    if summary:
        parts.append(summary)
    return "\n".join(parts)


def _deepseek_blocks(results: list[Any]) -> list[str]:
    blocks: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        block = _deepseek_result_block(cast("dict[str, Any]", result))
        if block:
            blocks.append(block)
    return blocks


def _deepseek_content(api_key: str, base_url: str | None, query: str, num_results: int) -> str:
    """DeepSeek 官方 Search 接口 → 渲染成结果块文本（web_search 的 deepseek 分支）。"""
    body = _deepseek_post(
        api_key,
        _deepseek_search_url(base_url),
        {"query": query, "count": min(max(1, num_results), _DEEPSEEK_MAX_SEARCH_COUNT)},
        _DEEPSEEK_SEARCH_TIMEOUT,
    )
    blocks = _deepseek_blocks(body.get("results") or [])
    if not blocks:
        raise ValueError("DeepSeek search returned no results")
    return "\n\n".join(blocks)


def _deepseek_page_block(api_key: str, base_url: str | None, url: str) -> str:
    """抓单页，返回与 Exa 分支同形的 ``### 标题 + URL + Markdown 正文`` 块。

    正文按 ``_PAGE_MAX_CHARS`` 截断——与 Exa 分支同一口径，避免超长文档把整页
    塞进 agent 上下文。失败（401/402/403/404/429、超时）抛异常，由调用方按
    「单个 URL 失败」处理。
    """
    body = _deepseek_post(
        api_key,
        _deepseek_fetch_url(base_url),
        {"url": url},
        _DEEPSEEK_FETCH_TIMEOUT,
    )
    text = str(body.get("content") or "").strip()
    if not text:
        raise ValueError("DeepSeek fetch returned no page content")
    if len(text) > _PAGE_MAX_CHARS:
        text = f"{text[:_PAGE_MAX_CHARS]}\n[truncated at {_PAGE_MAX_CHARS} characters]"
    title = str(body.get("title") or "").strip() or url
    return f"### {title}\n{url}\n\n{text}"


def _deepseek_get_contents(api_key: str, base_url: str | None, urls: list[str]) -> dict[str, Any]:
    """逐页调用 DeepSeek Fetch（顺序请求，天然落在账号 5 QPS 之内）。

    单个 URL 失败只记入 ``failed_urls``，不拖垮整批 —— 与 Exa 分支的对外契约一致。
    """
    blocks: list[str] = []
    fetched: set[str] = set()
    failed: list[str] = []
    reasons: list[str] = []
    for url in urls:
        try:
            blocks.append(_deepseek_page_block(api_key, base_url, url))
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            logger.warning("DeepSeek fetch rejected %s status=%s", url, status)
            failed.append(url)
            reasons.append(f"{url} -> HTTP {status}" if status else f"{url} -> HTTP error")
            continue
        except requests.exceptions.RequestException as exc:
            logger.warning("DeepSeek fetch network error for %s: %s", url, exc)
            failed.append(url)
            reasons.append(f"{url} -> network error")
            continue
        except (KeyError, IndexError, ValueError):
            logger.info("DeepSeek fetch returned no extractable content for %s", url)
            failed.append(url)
            reasons.append(f"{url} -> no extractable content")
            continue
        fetched.add(_normalize_url(url))

    if not blocks:
        return {
            "success": False,
            "provider": "deepseek",
            "error": (
                "DeepSeek fetch returned no content for any requested URL. "
                f"Details: {'; '.join(reasons) or 'unknown'}. "
                "Check the URLs are public and complete; HTTP 402 means the DeepSeek "
                "account is out of credit, 429 means the per-account QPS limit was hit "
                "(5/s for Search and Fetch)"
            ),
            "failed_urls": failed,
        }

    ok_urls = [url for url in urls if _normalize_url(url) in fetched]
    result: dict[str, Any] = {
        "success": True,
        "urls": ok_urls,
        "provider": "deepseek",
        "content": "\n\n".join(blocks),
    }
    if failed:
        logger.warning(
            "web_get_contents returned %d of %d pages (deepseek)",
            len(ok_urls),
            len(urls),
        )
        result["failed_urls"] = failed
        result["warning"] = (
            f"DeepSeek fetch returned no content for {len(failed)} of {len(urls)} requested "
            "URLs. Those pages are missing from the content below"
        )
    return result


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
    deepseek_key = (getattr(integrations, "deepseek_api_key", None) or "").strip()

    # 配了 DeepSeek key 时，页面抓取改走 DeepSeek ``/v1/tools/fetch``（不再依赖 Exa）。
    # 例外：provider 被显式钉在 exa 且确有 Exa key —— 抓取是 Exa 唯一独有的能力，
    # 那种「运维明确选了 Exa」的部署保持原路径，不被静默改写。
    # 未配 DeepSeek key 时下面整段原有逻辑一字不改（含所有报错文案）。
    if deepseek_key and not (provider == "exa" and integrations.exa_api_key):
        logger.info("web_get_contents via DeepSeek fetch urls=%d", len(cleaned))
        result = _deepseek_get_contents(
            deepseek_key,
            getattr(integrations, "deepseek_base_url", None),
            cleaned,
        )
        if result.get("success") or not integrations.exa_api_key:
            return result
        # DeepSeek 抓取整批失败（额度/限流/网络）而本部署还配了 Exa → 回落一次，
        # 别让一次上游抖动把这批 URL 直接判死。两条都失败则返回 DeepSeek 的原始错误。
        logger.info("web_get_contents failed over from deepseek to exa")
        fallback = _guarded_call(
            "Page fetch",
            "Page fetch was rejected. Check the URLs are complete, public, and correctly formed",
            lambda: _exa_page_text(integrations.exa_api_key, cleaned),
        )
        if isinstance(fallback, dict):
            return result
        content, fetched = fallback
        failed_over: dict[str, Any] = {
            "success": True,
            "urls": [url for url in cleaned if _normalize_url(url) in fetched],
            "provider": "exa",
            "note": (
                f"DeepSeek fetch failed ({(result.get('error') or '')[:120]}); "
                "fell back to Exa for these URLs"
            ),
            "content": content,
        }
        missing_urls = [url for url in cleaned if _normalize_url(url) not in fetched]
        if missing_urls:
            failed_over["failed_urls"] = missing_urls
        return failed_over

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
    """Real-time web search (Exa, Perplexity, self-hosted SearXNG, or DeepSeek)
    — your primary research tool.

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

    In ``auto`` mode, a provider that fails on auth / quota / rate limit
    / network fails over to the local SearXNG (then to key-free security
    databases); the result's ``note`` says so. A provider you pinned
    explicitly does not fail over — fix the key or switch it yourself.

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
    """Fetch the full, cleaned text of specific web pages (DeepSeek fetch, or Exa).

    Use this as the drill-down step after ``web_search``: when a result's
    summary is not enough, pass that result's URL here to read the whole
    page. Good for reading a full advisory, a CVE writeup,
    an exploit proof-of-concept, or vendor documentation end to end.

    Prefer ``web_search`` first to find the right pages, then fetch only
    the few URLs worth reading in full — each page can be large, so avoid
    fetching many pages you do not need.

    Page fetching needs either a configured DeepSeek key
    (``DEEPSEEK_API_KEY``) or the Exa provider (``EXA_API_KEY``). When
    neither is configured it returns an error and you should use
    ``web_search`` instead. If the DeepSeek fetch fails while an Exa key
    is also configured, it falls back to Exa and says so in ``note``.

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
