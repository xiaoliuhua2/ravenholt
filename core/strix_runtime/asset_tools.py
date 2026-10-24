"""ravenholt 的资产登记工具：把测绘到的新资产写回工作项目，并补结构边。

侦察子代理在沙箱里枚举出的子域 / 端口 / 服务此前只落在 ``/workspace`` 的清单文件里，
项目「资产」表看不到，攻击面图也不增长。``register_assets`` 把这类新资产以
``origin=discovered`` 落库（与用户手工录入的 ``scope`` 资产区分），并为
「域名 → 该域名上的服务」自动补一条 ``hosts`` 结构边。

容器/项目上下文从运行上下文的 dict 取：``work_project_id`` / ``session_id`` / ``agent_id``。
"""

from __future__ import annotations

import ipaddress
import json
from typing import Any

from agents import RunContextWrapper, function_tool

from schema.work_project.assets import (
    WorkProjectAssetOrigin,
    WorkProjectAssetRequest,
    WorkProjectAssetType,
)
from schema.work_project.graph import (
    WorkProjectAttackPathRequest,
    WorkProjectAttackPathStatus,
    WorkProjectAttackPathStepRequest,
    WorkProjectGraphEdgeRequest,
    WorkProjectGraphEdgeType,
)
from service.work_project.assets import (
    count_work_project_assets,
    find_work_project_asset,
    find_work_project_asset_by_identifier,
    search_work_project_assets,
    upsert_work_project_asset,
)
from service.work_project.graph import (
    create_work_project_attack_path,
    create_work_project_attack_path_step,
    delete_work_project_attack_path,
    upsert_work_project_graph_edge,
)

_MAX_BATCH = 100
_MAX_PATH_STEPS = 20
_MAX_LIST_LIMIT = 500
# 单项目 agent 自发现资产上限：再多的子域罗列对测评没有增量，只会撑大资产表与攻击面图。
_MAX_DISCOVERED_ASSETS = 5000
_EDGE_ALREADY_EXISTS = "graph edge already exists"


def _inner(ctx: RunContextWrapper) -> dict[str, Any]:
    return ctx.context if isinstance(ctx.context, dict) else {}


def _json(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


async def _ensure_hosts_edge(
    project_id: int,
    service,
    *,
    agent_code: str,
    session_id: str,
) -> str:
    """域名资产与服务资产之间补 ``hosts`` 边；没有同域名的 domain 资产就跳过。"""
    host = (service.host or "").strip().lower()
    if not host or _is_ip(host):
        return ""
    domain = await find_work_project_asset(project_id, WorkProjectAssetType.DOMAIN, host)
    if domain is None:
        return ""
    _, error = await upsert_work_project_graph_edge(
        project_id,
        WorkProjectGraphEdgeRequest(
            source_asset_id=domain.id,
            target_asset_id=service.id,
            type=WorkProjectGraphEdgeType.HOSTS,
            label="hosts",
        ),
        created_by_agent_code=agent_code,
        created_from_session_id=session_id,
    )
    if error and error != _EDGE_ALREADY_EXISTS:
        return f"edge failed: {error}"
    return "edge"


async def _register_one(
    project_id: int,
    entry: Any,
    *,
    agent_code: str,
    session_id: str,
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {"status": "error", "error": "asset entry must be an object"}
    try:
        request = WorkProjectAssetRequest(
            type=entry.get("type", ""),
            host=entry.get("host") or "",
            port=entry.get("port"),
            path=entry.get("path") or "",
        )
    except ValueError as exc:
        return {"input": entry, "status": "error", "error": str(exc)}

    existing = await find_work_project_asset(project_id, request.type, request.identifier)
    saved, error = await upsert_work_project_asset(
        project_id,
        request,
        created_by_agent_code=agent_code,
        created_from_session_id=session_id,
    )
    if saved is None:
        return {
            "input": entry,
            "status": "error",
            "error": error or "unknown",
            "identifier": request.identifier,
        }

    result: dict[str, Any] = {
        "identifier": saved.identifier,
        "type": saved.type.value,
        "status": "existing" if existing is not None else "created",
        "asset_id": saved.id,
    }
    if saved.type == WorkProjectAssetType.SERVICE:
        edge = await _ensure_hosts_edge(
            project_id, saved, agent_code=agent_code, session_id=session_id
        )
        if edge:
            result["edge"] = edge
    return result


async def _discovered_limit_error(project_id: int) -> str:
    """项目自发现资产达到上限时返回错误文案，否则返回空串。"""
    discovered = await count_work_project_assets(project_id, origin=WorkProjectAssetOrigin.DISCOVERED)
    if discovered < _MAX_DISCOVERED_ASSETS:
        return ""
    return (
        f"project discovered asset limit reached ({discovered}/{_MAX_DISCOVERED_ASSETS}); "
        "stop enumerating, register only assets that are actually in scope or on a path"
    )


@function_tool
async def register_assets(ctx: RunContextWrapper, assets_json: str) -> str:
    """Register newly discovered assets into the bound work project.

    Use this for assets the recon stage actually found (subdomains, hosts:ports,
    CIDRs, source/binary paths). Do NOT re-register the project's existing scope
    list: this tool is idempotent, but the reply only reports new value. Each call
    is appended to the project asset table with origin=discovered, and a service
    whose host matches an existing domain asset also gets a `hosts` graph edge.

    Args:
        assets_json: JSON array (max 100) of objects with keys
            `type` (domain|service|network|binary), `host` (domain / IP / CIDR;
            empty for binary), `port` (1-65535 for service), `path` (binary only).
            Example: [{"type":"domain","host":"api.example.com"},
                      {"type":"service","host":"api.example.com","port":8443}]

    Returns:
        JSON with ok, created, existing, failed counts plus a per-asset breakdown.
    """
    project_id = _inner(ctx).get("work_project_id")
    session_id = str(_inner(ctx).get("session_id") or "")
    agent_code = str(_inner(ctx).get("agent_id") or "")

    if not isinstance(project_id, int):
        return _json(ok=False, error="no work project bound: assets cannot be registered")

    raw = (assets_json or "").strip()
    if not raw:
        return _json(ok=False, error="assets_json is required")
    try:
        entries = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return _json(ok=False, error=f"assets_json is not valid JSON: {exc}")
    if not isinstance(entries, list) or not entries:
        return _json(ok=False, error="assets_json must be a non-empty JSON array")
    if len(entries) > _MAX_BATCH:
        return _json(ok=False, error=f"too many assets in one call (max {_MAX_BATCH})")

    limit_error = await _discovered_limit_error(project_id)
    if limit_error:
        return _json(ok=False, error=limit_error)

    results: list[dict[str, Any]] = []
    for entry in entries:
        try:
            results.append(await _register_one(
                project_id, entry, agent_code=agent_code, session_id=session_id
            ))
        except Exception as exc:  # noqa: BLE001 - tool errors must be model-visible results
            results.append({"input": entry, "status": "error", "error": f"register failed: {exc}"})

    created = sum(1 for item in results if item.get("status") == "created")
    existing = sum(1 for item in results if item.get("status") == "existing")
    failed = sum(1 for item in results if item.get("status") == "error")
    return _json(
        ok=failed == 0,
        created=created,
        existing=existing,
        failed=failed,
        results=results,
    )


async def _record_path(
    project_id: int,
    title: str,
    steps: Any,
    *,
    summary: str = "",
    status: str = "suspected",
    agent_code: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """登记一条利用链：步骤用资产标识表达，缺的边自动补。"""
    title = (title or "").strip()
    if not title:
        return {"ok": False, "error": "title is required"}
    try:
        status_value = WorkProjectAttackPathStatus(str(status or "suspected").strip().lower())
    except ValueError:
        return {"ok": False, "error": "status must be suspected|validated|blocked|closed"}
    if not isinstance(steps, list) or not steps:
        return {"ok": False, "error": "steps must be a non-empty JSON array"}
    if len(steps) > _MAX_PATH_STEPS:
        return {"ok": False, "error": f"too many steps (max {_MAX_PATH_STEPS})"}

    resolved: list[tuple[dict[str, Any], Any, Any]] = []
    missing: list[str] = []
    for entry in steps:
        if not isinstance(entry, dict):
            return {"ok": False, "error": "each step must be an object with from/to"}
        source_id = str(entry.get("from") or "").strip()
        target_id = str(entry.get("to") or "").strip()
        if not source_id or not target_id:
            return {"ok": False, "error": "each step needs 'from' and 'to' asset identifiers"}
        source = await find_work_project_asset_by_identifier(project_id, source_id)
        target = await find_work_project_asset_by_identifier(project_id, target_id)
        if source is None:
            missing.append(source_id)
        if target is None:
            missing.append(target_id)
        resolved.append((entry, source, target))
    if missing:
        return {
            "ok": False,
            "error": "unknown asset identifiers; register them with register_assets first",
            "missing": sorted(set(missing)),
        }

    path, error = await create_work_project_attack_path(
        project_id,
        WorkProjectAttackPathRequest(
            title=title,
            status=status_value,
            summary=(summary or "").strip(),
        ),
        created_by_agent_code=agent_code,
        created_from_session_id=session_id,
    )
    if path is None:
        return {"ok": False, "error": error or "creating attack path failed"}

    created_steps: list[dict[str, Any]] = []
    edges_created = 0
    try:
        for index, (entry, source, target) in enumerate(resolved, start=1):
            raw_type = str(entry.get("type") or WorkProjectGraphEdgeType.LEADS_TO.value).strip().lower()
            try:
                edge_type = WorkProjectGraphEdgeType(raw_type)
            except ValueError:
                raise ValueError(f"unknown edge type: {raw_type}")
            edge, edge_error = await upsert_work_project_graph_edge(
                project_id,
                WorkProjectGraphEdgeRequest(
                    source_asset_id=source.id,
                    target_asset_id=target.id,
                    type=edge_type,
                    label=str(entry.get("label") or ""),
                ),
                created_by_agent_code=agent_code,
                created_from_session_id=session_id,
            )
            if edge is None:
                raise ValueError(f"edge failed: {edge_error or 'unknown'}")
            edges_created += 1
            step, step_error = await create_work_project_attack_path_step(
                project_id,
                path.id,
                WorkProjectAttackPathStepRequest(sequence=index, edge_id=edge.id),
                created_by_agent_code=agent_code,
                created_from_session_id=session_id,
            )
            if step is None:
                raise ValueError(f"step {index} failed: {step_error or 'unknown'}")
            created_steps.append({
                "sequence": index,
                "edge_id": edge.id,
                "from": source.identifier,
                "to": target.identifier,
            })
    except Exception as exc:  # noqa: BLE001 - roll back the half-written chain
        await delete_work_project_attack_path(project_id, path.id)
        return {"ok": False, "error": str(exc) or "creating attack path failed"}

    return {
        "ok": True,
        "path_id": path.id,
        "status": path.status.value,
        "steps": created_steps,
        "edges": edges_created,
    }


@function_tool
async def record_attack_path(
    ctx: RunContextWrapper,
    title: str,
    steps_json: str,
    summary: str = "",
    status: str = "suspected",
) -> str:
    """Record one attack path (an ordered exploit chain) into the work project.

    Use this once a chain is actually established: entry asset → lateral move(s) →
    impact. Each step is a directed relation between two assets already registered
    in the project (call `register_assets` first); a missing edge is created with
    the step's type (default `leads_to`). The rendered 攻击路径 tab reads exactly
    these ordered edges, so an unrecorded chain stays invisible.

    Args:
        title: short Chinese title, e.g. "SSO 登出跳转 → 用户中心接管".
        steps_json: JSON array (max 20) of objects with keys
            `from` (asset identifier, e.g. "api.example.com" / "10.0.0.5:8443"),
            `to` (asset identifier), optional `type`
            (leads_to|exploits|pivots_to|trusts|connects_to|resolves_to|hosts|related)
            and optional `label`.
        summary: one paragraph: what access the chain starts from and what it reaches.
        status: suspected|validated|blocked|closed.

    Returns:
        JSON with ok, path_id, steps, edges, or an error (missing identifiers listed).
    """
    project_id = _inner(ctx).get("work_project_id")
    session_id = str(_inner(ctx).get("session_id") or "")
    agent_code = str(_inner(ctx).get("agent_id") or "")
    if not isinstance(project_id, int):
        return _json(ok=False, error="no work project bound: attack paths cannot be recorded")

    raw = (steps_json or "").strip()
    if not raw:
        return _json(ok=False, error="steps_json is required")
    try:
        steps = json.loads(raw)
    except (TypeError, ValueError) as exc:
        return _json(ok=False, error=f"steps_json is not valid JSON: {exc}")

    result = await _record_path(
        project_id,
        title,
        steps,
        summary=summary,
        status=status,
        agent_code=agent_code,
        session_id=session_id,
    )
    return _json(**result)


async def _list_assets(
    project_id: int,
    *,
    asset_type: str = "",
    query: str = "",
    origin: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """分页读项目资产；tool 只负责取运行上下文。"""
    type_value: WorkProjectAssetType | None = None
    raw_type = (asset_type or "").strip().lower()
    if raw_type:
        try:
            type_value = WorkProjectAssetType(raw_type)
        except ValueError:
            return {"ok": False, "error": "asset_type must be domain|service|network|binary"}
    origin_value: WorkProjectAssetOrigin | None = None
    raw_origin = (origin or "").strip().lower()
    if raw_origin:
        try:
            origin_value = WorkProjectAssetOrigin(raw_origin)
        except ValueError:
            return {"ok": False, "error": "origin must be scope|discovered"}

    page_size = max(1, min(int(limit or 50), _MAX_LIST_LIMIT))
    start = max(0, int(offset or 0))
    total, rows = await search_work_project_assets(
        project_id,
        keyword=query or "",
        asset_type=type_value,
        origin=origin_value,
        limit=page_size,
        offset=start,
    )
    return {
        "ok": True,
        "total": total,
        "offset": start,
        "limit": page_size,
        "has_more": start + len(rows) < total,
        "items": [
            {"type": row.type.value, "identifier": row.identifier, "origin": row.origin.value}
            for row in rows
        ],
    }


@function_tool
async def list_project_assets(
    ctx: RunContextWrapper,
    asset_type: str = "",
    query: str = "",
    origin: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List the bound work project's registered assets, paginated.

    The project's authorization list is injected each turn as a summary; once it is
    large the platform folds it by parent domain / host, so exact identifiers are not
    all in the prompt. Call this to read the real entries (e.g. the concrete subdomains
    under a folded parent) instead of guessing or re-enumerating.

    Args:
        asset_type: optional filter: domain|service|network|binary (empty = all).
        query: optional case-insensitive substring on identifier / host / path.
        origin: optional filter: scope (user-declared range) | discovered (agent-found).
        limit: page size, 1-500 (default 50).
        offset: rows to skip, for paging (default 0).

    Returns:
        JSON with ok, total, offset, limit, has_more and items
        (`type` / `identifier` / `origin`).
    """
    project_id = _inner(ctx).get("work_project_id")
    if not isinstance(project_id, int):
        return _json(ok=False, error="no work project bound: assets cannot be listed")
    return _json(**await _list_assets(
        project_id,
        asset_type=asset_type,
        query=query,
        origin=origin,
        limit=limit,
        offset=offset,
    ))


# 挂给 ravenholt root/child 的资产工具（仅在绑定了 WorkProject 时挂载）。
ASSET_TOOLS: tuple[Any, ...] = (register_assets, record_attack_path, list_project_assets)


__all__ = ["ASSET_TOOLS", "list_project_assets", "record_attack_path", "register_assets"]
