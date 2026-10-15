"""无 key 的安全数据源检索（NVD / OSV / CIRCL / GitHub / Exploit-DB）。

用途：当 `web_search` 没有配置任何 provider（Exa / Perplexity / 自建 SearXNG）时，
仍能拿到**直击靶心的漏洞情报**——CVE 详情、CVSS、受影响版本、PoC/利用仓库、
Exploit-DB 条目。全部是公开、免费的 HTTP 接口，**不需要任何 API key**。

定位：比通用搜索引擎更精准（查 CVE / PoC 直接命中），但**只覆盖安全数据**，
不能替代通用网页搜索。因此它是 `web_search` 的**降级兜底**，也是一个独立工具。

数据源（2026-10 实测在本部署网络内均可达）：

- NVD 2.0        ``keywordSearch`` 关键词查 CVE（匿名限速 ~5 次/30s）
- OSV.dev        按漏洞 ID 精确查询（CVE / GHSA / PYSEC / RUSTSEC…）
- CIRCL cve-search  ``/api/search/<vendor>/<product>`` 厂商-产品维度
- GitHub         仓库搜索（找 PoC / 利用脚本；匿名限速 ~10 次/分）
- Exploit-DB     站内 DataTables JSON（远程利用条目）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import requests
from agents import RunContextWrapper, function_tool

from strix.tools.nullish import is_nullish


if TYPE_CHECKING:
    from collections.abc import Callable


logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 25
_MAX_SNIPPET = 320
_ALL_SOURCES = ("nvd", "osv", "circl", "github", "exploitdb")

# 形如 CVE-2021-44228 / GHSA-jfh8-c2jp-5v3q / PYSEC-2021-1 / RUSTSEC-2021-0078
_ID_LIKE = re.compile(r"^(?:CVE|GHSA|PYSEC|GO|RUSTSEC|OSV|DSA|USN)-[\w.-]+$", re.IGNORECASE)
_CVE_IN_TEXT = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)


def _clip(text: Any, limit: int = _MAX_SNIPPET) -> str:
    value = str(text or "").strip().replace("\r", " ")
    value = re.sub(r"\s+", " ", value)
    return value[:limit] + ("…" if len(value) > limit else "")


def _get(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
    merged = {"User-Agent": "ravenholt-security-search/1.0", "Accept": "application/json"}
    if headers:
        merged.update(headers)
    return requests.get(url, params=params, headers=merged, timeout=_HTTP_TIMEOUT)


# --------------------------------------------------------------------------- NVD


def _nvd(query: str, limit: int) -> list[dict[str, Any]]:
    response = _get(
        "https://services.nvd.nist.gov/rest/json/cves/2.0",
        params={"keywordSearch": query, "resultsPerPage": max(1, min(limit, 20))},
    )
    response.raise_for_status()
    body = response.json()
    out: list[dict[str, Any]] = []
    for item in body.get("vulnerabilities") or []:
        cve = (item or {}).get("cve") or {}
        cve_id = str(cve.get("id") or "")
        if not cve_id:
            continue
        desc = ""
        for d in cve.get("descriptions") or []:
            if isinstance(d, dict) and d.get("lang") == "en":
                desc = str(d.get("value") or "")
                break
        score = severity = None
        metrics = cve.get("metrics") or {}
        for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            entries = metrics.get(key) or []
            if entries:
                data = (entries[0] or {}).get("cvssData") or {}
                score = data.get("baseScore")
                severity = data.get("baseSeverity") or (entries[0] or {}).get("baseSeverity")
                break
        out.append({
            "source": "NVD",
            "id": cve_id,
            "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            "title": f"{cve_id}" + (f" (CVSS {score} {severity})" if score else ""),
            "snippet": _clip(desc),
            "published": str(cve.get("published") or "")[:10],
        })
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- OSV


def _osv(query: str, limit: int) -> list[dict[str, Any]]:
    candidate = query.strip().upper()
    if not _ID_LIKE.match(candidate):
        return []
    response = _get(f"https://api.osv.dev/v1/vulns/{quote(candidate)}")
    if response.status_code == 404:
        return []
    response.raise_for_status()
    body = response.json()
    vuln_id = str(body.get("id") or candidate)
    aliases = [str(a) for a in (body.get("aliases") or [])]
    severity = ""
    for entry in body.get("severity") or []:
        if isinstance(entry, dict) and entry.get("score"):
            severity = str(entry["score"])[:60]
            break
    detail = str(body.get("details") or "") or str(body.get("summary") or "")
    return [{
        "source": "OSV",
        "id": vuln_id,
        "url": f"https://osv.dev/vulnerability/{vuln_id}",
        "title": f"{vuln_id}" + (f" (aliases: {', '.join(aliases)})" if aliases else ""),
        "snippet": _clip(detail + (f" | severity: {severity}" if severity else "")),
        "published": str(body.get("published") or "")[:10],
    }]


# --------------------------------------------------------------------------- CIRCL


def _circl_extract(record: dict[str, Any]) -> dict[str, Any] | None:
    meta = record.get("cveMetadata") or {}
    cve_id = str(meta.get("cveId") or "")
    if not cve_id:
        return None
    cna = (record.get("containers") or {}).get("cna") or {}
    desc = ""
    for d in cna.get("descriptions") or []:
        if isinstance(d, dict) and d.get("lang") == "en" and d.get("value"):
            desc = str(d["value"])
            break
    if not desc:
        for d in cna.get("descriptions") or []:
            if isinstance(d, dict) and d.get("value"):
                desc = str(d["value"])
                break
    score = None
    for metric in cna.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        for key in ("cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"):
            blob = metric.get(key)
            if isinstance(blob, dict) and blob.get("baseScore") is not None:
                score = blob.get("baseScore")
                break
        if score is not None:
            break
    title = str(cna.get("title") or cve_id)
    return {
        "source": "CIRCL",
        "id": cve_id,
        "url": f"https://cve.circl.lu/cve/{cve_id}",
        "title": title + (f" (CVSS {score})" if score else ""),
        "snippet": _clip(desc),
        "published": str(meta.get("datePublished") or "")[:10],
    }


def _circl(query: str, limit: int) -> list[dict[str, Any]]:
    words = [w for w in re.split(r"[\s/]+", query.strip()) if w]
    if len(words) < 2:  # CIRCL 的 search 端点需要 vendor 与 product 两个路径段
        return []
    url = f"https://cve.circl.lu/api/search/{quote(words[0].lower())}/{quote(words[1].lower())}"
    response = _get(url)
    if response.status_code >= 400:
        return []
    body = response.json()
    groups = (body.get("results") or {}) if isinstance(body, dict) else {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("nvd", "cvelistv5"):
        for entry in groups.get(key) or []:
            record = None
            if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict):
                record = entry[1]
            elif isinstance(entry, dict):
                record = entry
            if not record:
                continue
            extracted = _circl_extract(record)
            if extracted and extracted["id"] not in seen:
                seen.add(extracted["id"])
                out.append(extracted)
            if len(out) >= limit:
                return out
    return out


# --------------------------------------------------------------------------- GitHub


def _github(query: str, limit: int) -> list[dict[str, Any]]:
    response = _get(
        "https://api.github.com/search/repositories",
        params={"q": query, "per_page": max(1, min(limit, 10)), "sort": "stars", "order": "desc"},
        headers={"Accept": "application/vnd.github+json"},
    )
    if response.status_code >= 400:
        return []
    body = response.json()
    out: list[dict[str, Any]] = []
    for item in body.get("items") or []:
        full_name = str(item.get("full_name") or "")
        if not full_name:
            continue
        out.append({
            "source": "GitHub",
            "id": full_name,
            "url": str(item.get("html_url") or ""),
            "title": f"{full_name} ★{item.get('stargazers_count', 0)}",
            "snippet": _clip(item.get("description") or ""),
            "published": str(item.get("updated_at") or "")[:10],
        })
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- Exploit-DB


def _exploitdb(query: str, limit: int) -> list[dict[str, Any]]:
    response = _get(
        "https://www.exploit-db.com/search",
        params={"q": query, "draw": 1, "start": 0, "length": max(1, min(limit, 20))},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    if response.status_code >= 400:
        return []
    body = response.json()
    out: list[dict[str, Any]] = []
    for row in body.get("data") or []:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or "")
        desc = row.get("description")
        if isinstance(desc, list):
            desc = desc[-1] if desc else ""
        cves = [
            str(c.get("code"))
            for c in (row.get("code") or [])
            if isinstance(c, dict) and str(c.get("code_type") or "").lower() == "cve"
        ]
        out.append({
            "source": "Exploit-DB",
            "id": eid,
            "url": f"https://www.exploit-db.com/exploits/{eid}",
            "title": f"EDB-{eid} {_clip(desc, 120)}"
                     + (f" [{', '.join(cves[:3])}]" if cves else ""),
            "snippet": f"{row.get('type_id', '')} / {row.get('platform_id', '')}"
                       f" · 发布 {row.get('date_published', '')}",
            "published": str(row.get("date_published") or "")[:10],
        })
        if len(out) >= limit:
            break
    return out


_SOURCES: dict[str, Callable[[str, int], list[dict[str, Any]]]] = {
    "nvd": _nvd,
    "osv": _osv,
    "circl": _circl,
    "github": _github,
    "exploitdb": _exploitdb,
}


def _format_blocks(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in results:
        head = f"### [{item.get('source')}] {item.get('title') or item.get('id')}"
        if item.get("published"):
            head += f"  ·  {item['published']}"
        block = f"{head}\n{item.get('url', '')}"
        if item.get("snippet"):
            block += f"\n{item['snippet']}"
        lines.append(block)
    return "\n\n".join(lines)


# 结果短缓存：agent 常对同一关键词反复检索；缓存可显著降低 GitHub 匿名限速
# （~10 次/分）与 NVD（匿名 ~5 次/30s）的压力。
_CACHE_TTL_SECONDS = 120.0
_CACHE_MAX_ENTRIES = 256
_cache: dict[tuple[str, tuple[str, ...], int], tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _cache_get(key: tuple[str, tuple[str, ...], int]) -> dict[str, Any] | None:
    with _cache_lock:
        hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
        return hit[1]
    return None


def _cache_put(key: tuple[str, tuple[str, ...], int], value: dict[str, Any]) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            _cache.clear()
        _cache[key] = (time.monotonic(), value)


def collect_security_results(
    query: str,
    *,
    sources: tuple[str, ...] = _ALL_SOURCES,
    limit: int = 5,
) -> dict[str, Any]:
    """并发查询各数据源，返回 ``{"results": [...], "failures": {...}, "content": str}``。

    同步函数（内部用线程池并发），供工具与 ``web_search`` 降级路径共用；结果带短缓存。
    """
    chosen = [s for s in sources if s in _SOURCES] or list(_ALL_SOURCES)
    cache_key = (query.strip().lower(), tuple(sorted(chosen)), limit)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results: list[dict[str, Any]] = []
    failures: dict[str, str] = {}

    def run(name: str) -> tuple[str, list[dict[str, Any]] | str]:
        try:
            return name, _SOURCES[name](query, limit)
        except Exception as exc:  # noqa: BLE001 - 单源失败不影响其它源
            logger.debug("security_search source %s failed: %s", name, exc)
            return name, f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=len(chosen)) as pool:
        for name, outcome in pool.map(run, chosen):
            if isinstance(outcome, list):
                results.extend(outcome)
            else:
                failures[name] = outcome

    # 同源内按打分/星标已排好，这里只做稳定性排序：CVE 类优先
    results.sort(key=lambda r: (0 if str(r.get("id", "")).upper().startswith("CVE") else 1))
    payload = {"results": results, "failures": failures, "content": _format_blocks(results)}
    _cache_put(cache_key, payload)
    return payload


@function_tool(timeout=200)
async def security_search(ctx: RunContextWrapper, query: str, sources: str = "all", limit: int = 5) -> str:
    """Key-free lookup of **vulnerability intelligence** — NVD, OSV, CIRCL, GitHub, Exploit-DB.

    Use this when you need hard facts about a vulnerability rather than general
    web pages: CVE identifiers, CVSS scores, affected version ranges, exploits /
    PoC repositories, and Exploit-DB entries. **No API key is required**, so this
    still works when ``web_search`` reports "not configured".

    Best for:
    - "which CVEs affect <product> <version>" (NVD keyword, CIRCL vendor/product)
    - exact lookups of a known id: ``CVE-2021-44228``, ``GHSA-…``, ``PYSEC-…``
    - finding PoC / exploit tooling on GitHub or Exploit-DB for a CVE

    Not for: generic web research, blog posts, docs, OSINT on a company —
    that is ``web_search``'s job (and ``web_search`` falls back to this
    automatically when no provider key is configured).

    Args:
        query: What to look up. A product/version ("apache log4j 2.14"),
            a keyword ("spring4shell"), or an exact id ("CVE-2021-44228").
        sources: Comma-separated subset of ``nvd,osv,circl,github,exploitdb``,
            or ``all`` (default).
        limit: Max results per source (1-20).
    """
    if is_nullish(query) or not str(query).strip():
        return json.dumps({"success": False, "error": "Query cannot be empty"}, ensure_ascii=False)

    if is_nullish(sources) or str(sources).strip().lower() in ("", "all"):
        chosen = _ALL_SOURCES
    else:
        chosen = tuple(
            s.strip().lower() for s in str(sources).split(",") if s.strip().lower() in _SOURCES
        ) or _ALL_SOURCES

    limit = max(1, min(int(limit or 5), 20))
    payload = await asyncio.to_thread(collect_security_results, str(query), sources=chosen, limit=limit)
    results = payload["results"]
    return json.dumps(
        {
            "success": bool(results),
            "query": str(query),
            "sources_used": list(chosen),
            "count": len(results),
            "results": results,
            "failures": payload["failures"],
            "content": payload["content"] or "No results from the security databases for this query.",
        },
        ensure_ascii=False,
        default=str,
    )


__all__ = ["security_search", "collect_security_results"]
