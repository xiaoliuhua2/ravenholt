"""Self-test for the deterministic skill-routing table (feature ④).

Offline: no DB / no HTTP / no model calls. Run from the project root:

    .venv/bin/python scripts/verify_skill_routes_selftest.py              # POSIX
    .venv\\Scripts\\python.exe scripts\\verify_skill_routes_selftest.py   # Windows

It checks:
  1. the factory-default table loads and every referenced skill resolves in the
     strix loader (no typos / no stale skill names);
  2. unknown skill names are filtered out instead of being handed to the agent;
  3. fingerprints route deterministically to the expected skills;
  4. an unmatched observation falls back to the ``打穿短表`` index skill;
  5. the result never exceeds ``max_skills``;
  6. instance-override merge semantics (same-id replace / disabled_routes / add);
  7. the ``route_skills`` tool is actually wired into root+child tool sets, and
     routed skills are rendered into the child system prompt.

Exit code is non-zero if any expectation fails.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from core.strix_runtime.prompts import CHILD_PROTOCOL, build_child_instructions  # noqa: E402
from core.strix_runtime.skill_routes import (  # noqa: E402
    DEFAULT_ROUTES_FILE,
    SKILL_ROUTE_TOOLS,
    load_skill_routes,
    match_skills,
    merge_routes,
    unknown_skills,
)
from core.strix_runtime.skill_routes import _known_skill_names, _load_raw, _validate  # noqa: E402

checks: list[tuple[str, bool]] = []


def _check(name: str, ok: bool) -> None:
    checks.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def _skills_of(observed: str) -> list[str]:
    return list(match_skills(observed).skills)


def main() -> int:
    config = load_skill_routes()
    known = _known_skill_names()
    print(f"[routes] source={DEFAULT_ROUTES_FILE.name} routes={len(config.routes)} known_skills={len(known)}")

    # 1) 工厂默认表引用的技能名全部可解析
    missing = unknown_skills(config, known)
    print(f"[routes] unknown skill references = {missing}")
    _check("1 工厂默认表引用的技能名全部存在", not missing)
    _check("1 兜底技能 打穿短表 存在", "src_hunt/打穿短表" in known)

    # 2) 未知技能被过滤，不会交给 agent
    bogus = _validate(
        {
            "max_skills": 5,
            "routes": [{"id": "bogus", "signals": ["zzz"], "skills": ["src_hunt/__nope__"]}],
        },
        Path("<inline>"),
    )
    filtered = list(match_skills("zzz", bogus, known=known).skills)
    print(f"[routes] bogus route skills after filter = {filtered}")
    _check("2 未知技能被过滤（不返回非法技能名）", filtered == [])
    kept = list(match_skills("zzz", bogus, known=set()).skills)
    _check("2b 不传 known 时不做过滤（纯匹配语义）", kept == ["src_hunt/__nope__"])

    # 3) 指纹 → 确定性技能集
    cases: list[tuple[str, str]] = [
        ("站点返回 412 且带动态 cookie 与 _ts 脚本", "src_hunt/river-security-bypass"),
        ("对象存储 STS 领签，policy 可覆盖他人对象", "src_hunt/file-upload-test"),
        ("列表按 tenantId 过滤，可换 id 越权读他人数据", "src_hunt/idor-test"),
        ("小程序抓包拿到 lxCode 票据，换台客户端重放", "src_hunt/miniprogram-capture-token"),
        ("未登录发签口下发 signKey / AppSecret", "src_hunt/authbypass-test"),
        ("实名核验接口把姓名和证件号分开报错", "src_hunt/verification-oracle-enum"),
    ]
    for observed, expected in cases:
        got = _skills_of(observed)
        print(f"[routes] '{observed[:18]}…' -> {got}")
        _check(f"3 命中 {expected}（{observed[:12]}…）", expected in got)

    # 3b) 同一输入两次结果一致（确定性）
    a, b = _skills_of("对象存储 STS 领签"), _skills_of("对象存储 STS 领签")
    _check("3b 同一指纹两次路由结果一致", a == b and a != [])

    # 4) 无命中 → 回退短表
    none_result = match_skills("完全无关的一段描述 abcxyz")
    print(f"[routes] fallback skills = {list(none_result.skills)} used_fallback={none_result.used_fallback}")
    _check(
        "4 无指纹命中时回退 打穿短表",
        none_result.used_fallback and list(none_result.skills) == ["src_hunt/打穿短表"],
    )

    # 5) 不超过 max_skills
    wide = match_skills("未登录 越权 sql 注入 xss ssrf 上传 缓存 host 头 请求走私 逻辑 竞态 graphql")
    print(f"[routes] wide match = {len(wide.skills)} skills (max_skills={config.max_skills})")
    _check("5 技能数不超过 max_skills", len(wide.skills) <= config.max_skills)

    # 6) 实例覆盖：同 id 替换 + disabled_routes 移除 + 新增
    with tempfile.TemporaryDirectory() as tmp:
        override_path = Path(tmp) / "skill_routes.yaml"
        override_path.write_text(
            "disabled_routes:\n  - cors\n"
            "routes:\n"
            "  - id: idor\n"
            "    signals: [自研字段]\n"
            "    skills: [src_hunt/idor-test]\n"
            "  - id: brand-new\n"
            "    signals: [全新指纹]\n"
            "    skills: [src_hunt/info-leak-test]\n",
            encoding="utf-8",
        )
        base_raw = _load_raw(DEFAULT_ROUTES_FILE)
        base = _validate(base_raw, DEFAULT_ROUTES_FILE)
        override_raw = _load_raw(override_path)
        merged = merge_routes(base, base_raw, _validate(override_raw, override_path), override_raw)
    ids = [route.id for route in merged.routes]
    replaced = next(route for route in merged.routes if route.id == "idor")
    print(f"[routes] merged routes={len(ids)} cors_removed={'cors' not in ids} idor_signals={replaced.signals}")
    _check("6 同 id 条目被替换", replaced.signals == ["自研字段"])
    _check("6b disabled_routes 生效（cors 被移除）", "cors" not in ids)
    _check("6c 新增条目生效", "brand-new" in ids)
    _check("6d 非覆盖的默认条目保留", "waf-bypass" in ids)

    # 7) 工具接线 + 子代理预置技能块
    tool_names = [getattr(tool, "name", "") for tool in SKILL_ROUTE_TOOLS]
    print(f"[wire] SKILL_ROUTE_TOOLS = {tool_names}")
    _check("7 route_skills 工具已定义", tool_names == ["route_skills"])

    try:
        from core.strix_runtime import build_agent

        agent = build_agent(
            name="selftest",
            model="gpt-4o-mini",
            is_root=True,
            instructions="test",
            extra_tools=SKILL_ROUTE_TOOLS,
        )
        names = [getattr(tool, "name", "") for tool in agent.tools]
        child = build_agent(
            name="child",
            model="gpt-4o-mini",
            is_root=False,
            instructions=build_child_instructions(skills=["src_hunt/idor-test"]),
            extra_tools=SKILL_ROUTE_TOOLS,
        )
        print(f"[wire] root tools={len(names)} child has preset block={'预置技能' in child.instructions}")
        _check("7b root 工具集含 route_skills", "route_skills" in names)
        _check("7c child 工具集含 route_skills", "route_skills" in [t.name for t in child.tools])
        _check("7d child 系统提示渲染了预置技能块", "src_hunt/idor-test" in child.instructions)
        # 非交互回合必须补挂 wait_for_user：模型会从 wait_for_agents 的工具描述里得知它存在并调用，
        # 未注册会以 ModelBehaviorError 把整轮打成 failed（工具集里没有该名字即视为回归）。
        _check("7b2 非交互回合注册 wait_for_user", "wait_for_user" in names)
        interactive_agent = build_agent(
            name="probe",
            model="gpt-4o-mini",
            is_root=True,
            instructions="test",
            interactive=True,
        )
        _check(
            "7b3 交互回合不重复注册 wait_for_user（无重名冲突）",
            [tool.name for tool in interactive_agent.tools].count("wait_for_user") == 1,
        )
    except Exception as exc:  # noqa: BLE001 - 接线失败必须显式暴露
        print(f"[wire] building agent failed: {exc}")
        _check("7b root 工具集含 route_skills", False)
        _check("7c child 工具集含 route_skills", False)
        _check("7d child 系统提示渲染了预置技能块", False)

    _check(
        "7e 无技能时不追加预置块",
        CHILD_PROTOCOL in build_child_instructions()
        and "本流程策展的确定性技能集" not in build_child_instructions()
        and "本流程策展的确定性技能集" not in build_child_instructions(skills=[]),
    )

    from core.strix_runtime import prompts as prompts_module  # noqa: PLC0415

    _check(
        "7e2 语言纪律已前置注入 root / child 规程",
        prompts_module.build_root_instructions().startswith(prompts_module.LANGUAGE_DISCIPLINE)
        and build_child_instructions().startswith(prompts_module.LANGUAGE_DISCIPLINE)
        and build_child_instructions(skills=["src_hunt/idor-test"]).startswith(prompts_module.LANGUAGE_DISCIPLINE),
    )

    # 7f) 作战规程分轨：源码审计项目走白盒协议，渗透项目逐字不变
    pentest_root = prompts_module.build_root_instructions()
    audit_root = prompts_module.build_root_instructions(mode=prompts_module.RuntimeMode.SOURCE_AUDIT)
    _check(
        "7f 白盒 mode 切到源码审计规程",
        "源码审计主控" in audit_root and "渗透主控" not in audit_root
        and "渗透主控" in pentest_root and "源码审计主控" not in pentest_root,
    )
    _check(
        "7f2 白盒规程引用 src-hunt 白盒主流程与容器内源码目录",
        "src_hunt/06-researcher-blackbox-whitebox" in audit_root
        and "Phase 0" in audit_root
        and "/workspace/demo" in prompts_module.build_root_instructions(
            mode=prompts_module.RuntimeMode.SOURCE_AUDIT, source_roots=["demo"],
        ),
    )
    _check(
        "7f3 白盒 child 追加审计补充段",
        "白盒补充" in build_child_instructions(mode=prompts_module.RuntimeMode.SOURCE_AUDIT)
        and "白盒补充" not in build_child_instructions(),
    )

    # 7g) 技能路由分轨：白盒指纹命中 src-hunt 白盒主流程，白盒兜底不再回退渗透短表
    _check(
        "7g 白盒指纹命中 06 白盒主流程",
        "src_hunt/06-researcher-blackbox-whitebox"
        in list(match_skills("白盒 源码审计 语义审计").skills),
    )
    _check(
        "7g2 依赖指纹命中 dependency_cve_scanning",
        "custom/dependency_cve_scanning" in list(match_skills("检查 lockfile 依赖 CVE 供应链").skills),
    )
    audit_fallback = list(match_skills("qzxvbnm", known=known).skills)
    audit_mode_fallback = list(
        match_skills("qzxvbnm", mode=prompts_module.RuntimeMode.SOURCE_AUDIT, known=known).skills
    )
    _check(
        "7g3 白盒兜底用 06 白盒主流程（渗透仍回退打穿短表）",
        audit_fallback == ["src_hunt/打穿短表"]
        and audit_mode_fallback == ["src_hunt/06-researcher-blackbox-whitebox"],
    )

    # 8) 双轨已砍：原生 registry 轨道（core.agent.specs / core.tools.src_hunt / core.agent.registry）
    #    已不再被任何运行路径使用，相关断言一并移除。运行时只剩 strix 原生轨道：
    #    一个 root（build_agent）+ 自己 create_agent 派子代理 + 自己用 SDK Shell 调沙箱。
    _check(
        "8 双轨已砍：运行时不再暴露 build_runtime_agent",
        not hasattr(__import__("core.strix_runtime", fromlist=["x"]), "build_runtime_agent"),
    )

    print("=" * 60)
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"skill-routes self-test -> {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
