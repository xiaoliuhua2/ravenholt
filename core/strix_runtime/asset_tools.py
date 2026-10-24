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
    WorkProjectAssetRequest,
    WorkProjectAssetType,
)
from schema.work_project.graph import (
    WorkProjectGraphEdgeRequest,
    WorkProjectGraphEdgeType,
)
from service.work_project.assets import find_work_project_asset, upsert_work_project_asset
from service.work_project.graph import upsert_work_project_graph_edge

_MAX_BATCH = 100
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


# 挂给 ravenholt root/child 的资产工具（仅在绑定了 WorkProject 时挂载）。
ASSET_TOOLS: tuple[Any, ...] = (register_assets,)


__all__ = ["ASSET_TOOLS", "register_assets"]
