"""Four-dimension differential analysis for evidence.

The diff is intentionally deterministic: it normalises away volatile fields
(timestamps, nonces, tokens, fingerprints, ...) and then compares status code,
normalised length, normalised content hash, business code and total/count.

The result feeds the independent verifier's verdict. No LLM is involved.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


# --- normalisation ---------------------------------------------------------

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# timestamp shapes: ISO-8601, slash date-time, bare clock, epoch s/ms
_TS_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"),
    re.compile(r"\d{4}/\d{2}/\d{2}[ T]\d{2}:\d{2}:\d{2}"),
    re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"),
    re.compile(r"\b\d{10,13}\b"),
]

# keys whose *value* is volatile and must be masked regardless of content
_DYNAMIC_KEYS = (
    "nonce|csrf|csrftoken|xsrf|xsrftoken|token|access_token|session|sessionid|"
    "session_id|sid|_token|timestamp|ts|time|date|datetime|build|buildid|build_id|"
    "hash|rev|revision|sign|signature|requestid|request_id|traceid|trace_id"
)
_JSON_KV_RE = re.compile(rf'(?i)("(?:{_DYNAMIC_KEYS})"\s*:\s*)("[^"]*"|\d+)')
_FORM_KV_RE = re.compile(rf"(?i)\b({_DYNAMIC_KEYS})\s*=\s*([^&\s;\"']*)")
_HEADER_KV_RE = re.compile(rf"(?i)\b({_DYNAMIC_KEYS}):\s*([^\s;,]+)")

# cache-busting / fingerprint query params like ?v=1.2.3 or &ver=ab12
_FINGERPRINT_RE = re.compile(r"(?i)([?&])(?:v|ver|version|_v|t|ts)=([^&\s\"']+)")

# hashed asset filenames, e.g. app.9f3a2b1c.js
_ASSET_HASH_RE = re.compile(
    r"\b([A-Za-z0-9_\-]+)\.([0-9a-fA-F]{8,})\.(js|css|map|png|jpe?g|gif|svg|woff2?|ico)\b"
)

# long hex blobs (md5 / sha1 / sha256 / sha512)
_HEX_HASH_RE = re.compile(r"\b[0-9a-fA-F]{32,128}\b")


def normalize(text: str) -> str:
    """Mask volatile/dynamic fields so two structurally equal bodies compare equal."""
    if not text:
        return ""

    out = str(text)
    for pattern in _TS_PATTERNS:
        out = pattern.sub("<TS>", out)
    out = _UUID_RE.sub("<UUID>", out)

    # JSON-style "key": "value" / "key": 123
    out = _JSON_KV_RE.sub(lambda m: f'{m.group(1)}"<DYN>"', out)
    # query / form style key=value
    out = _FORM_KV_RE.sub(lambda m: f"{m.group(1)}=<DYN>", out)
    # header style key: value
    out = _HEADER_KV_RE.sub(lambda m: f"{m.group(1)}: <DYN>", out)
    # fingerprint query params
    out = _FINGERPRINT_RE.sub(lambda m: f"{m.group(1)}<FP>", out)
    # hashed asset filenames then bare long hex hashes
    out = _ASSET_HASH_RE.sub(lambda m: f"{m.group(1)}.<HASH>.{m.group(3)}", out)
    out = _HEX_HASH_RE.sub("<HASH>", out)
    return out


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def _load_json(text: str) -> Any:
    if not text:
        return None
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _find_key(data: Any, keys: tuple[str, ...]) -> tuple[str, Any] | None:
    """Depth-first search for the first occurrence of any of ``keys``."""
    if isinstance(data, dict):
        for key in keys:
            if key in data:
                return key, data[key]
        for value in data.values():
            found = _find_key(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_key(item, keys)
            if found is not None:
                return found
    return None


_BIZ_KEYS = ("code", "result", "errCode", "returnCode")
_TOTAL_KEYS = ("total", "totalNum", "totalSize", "count")


def four_dim_diff(
    baseline_status: int,
    baseline_body: str,
    probe_status: int,
    probe_body: str,
) -> dict[str, Any]:
    """Compare a baseline and a probe response across four dimensions.

    Dimensions: status code, normalised length, normalised content hash,
    business code, and total/count. Returns a stable dict used by the
    verifier (and stored verbatim in ``Evidence.diff_json``).
    """
    baseline_norm = normalize(baseline_body or "")
    probe_norm = normalize(probe_body or "")
    len_baseline = len(baseline_norm)
    len_probe = len(probe_norm)
    longest = max(len_baseline, len_probe)

    len_abs = abs(len_baseline - len_probe)
    len_ratio = (len_abs / longest) if longest else 0.0
    len_changed = len_abs > max(200, int(0.05 * longest))

    status_changed = baseline_status != probe_status
    content_hash_changed = _hash(baseline_norm) != _hash(probe_norm)

    baseline_json = _load_json(baseline_body or "")
    probe_json = _load_json(probe_body or "")

    baseline_biz = _find_key(baseline_json, _BIZ_KEYS)
    probe_biz = _find_key(probe_json, _BIZ_KEYS)
    bizcode_changed = baseline_biz != probe_biz

    baseline_total = _find_key(baseline_json, _TOTAL_KEYS)
    probe_total = _find_key(probe_json, _TOTAL_KEYS)
    total_changed = baseline_total != probe_total

    changed = (
        status_changed
        or len_changed
        or content_hash_changed
        or bizcode_changed
        or total_changed
    )

    if status_changed or bizcode_changed or total_changed or (content_hash_changed and len_changed):
        verdict_hint = "STRONG"
    elif content_hash_changed or len_changed:
        verdict_hint = "WEAK"
    else:
        verdict_hint = "NONE"

    return {
        "status_changed": status_changed,
        "len_abs": len_abs,
        "len_ratio": round(len_ratio, 6),
        "content_hash_changed": content_hash_changed,
        "bizcode_changed": bizcode_changed,
        "total_changed": total_changed,
        # extras (kept for readability / downstream use)
        "len_changed": len_changed,
        "changed": changed,
        "verdict_hint": verdict_hint,
    }
