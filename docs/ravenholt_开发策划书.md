# ravenholt 项目开发策划书

> 版本：v0.1（策划稿）
> 日期：2026-10-11
> 定位一句话：**ravenholt = 自主渗透测试平台** —— 以 **XuanMu 为平台骨架与前端底座**，接 **Strix 的渗透执行引擎**，灌 **src-hunt 的渗透方法论与报告口径**，再叠 **用户可控制的渗透策略治理层**。
> 本文档取代此前的《渗透测试Agent 开发策划书 / 开发规格书》（**旧文档作废**）。

---

## 一、三源融合边界

| 来源 | 取什么 | 怎么取 | 不取什么 |
|------|--------|--------|----------|
| **XuanMu**（MIT） | FastAPI 控制面 + PostgreSQL + React 操作台 + WS 实时流 + 会话池 + WorkProject 结构化记录 + Blackboard 推理图 + novnc 可视化 | **fork 当骨架** | 静态专家角色表、**本地 shell 模式**（`core/tools/local_shell.py`） |
| **Strix**（Apache-2.0） | 渗透 agent 编排（动态派生）+ Kali 工具链 + Caido 抓包/重放 + SARIF/CVSS + 预算控制 + MCP + CI + 沙箱运行时 | **能力全量保留**，作为流程引擎接入 | 不改其方法论取向（由 src-hunt 覆盖） |
| **src-hunt** | 演练阶段骨架（一种子闭环 / 进站 §4 / 全类型矩阵 / 闸门）+ 62 篇知识库 + 打穿短表 + 中文 7 段报告 + 差分纪律 | **双轨**：阶段骨架硬编码 + 技能包按需 `load_skill` | CORS（不挖）、白盒 Phase0~6 作为后续期 |
| **自有** | 渗透策略控制台 + 强制授权范围 + 审计 | 新增 | — |

**许可结论**：两者均可 fork / 修改 / 商用 / 闭源（保留版权与许可声明）。

---

## 二、需求确认表（28 项，已逐项对齐）

| # | 维度 | 结论 |
|---|------|------|
| 1 | 代码基线 | **fork XuanMu 当骨架** |
| 2 | 角色体系 | **改成动态派生**（弃 XuanMu 静态专家表，采 Strix `create_agent`） |
| 3 | 自主度 | **可切换**：默认无人值守，可开人在环 |
| 4 | 运行环境 | **混合**：平台/前端/DB 在 Windows 本机，渗透执行在 Docker 沙箱 |
| 5 | 执行沙箱 | **镜像合并、控制面单一**：以 Strix 的 Python 沙箱侧为主（Kali + Caido）；XuanMu 的出口控制/低频低感知作为**策略插件**移植；novnc 保留 |
| 6 | 报告口径 | **两套都要**：中文 `03` 七段 SRC 报告 + 完整 SARIF/CVSS |
| 7 | src-hunt 接入 | **双轨**：阶段骨架 + 技能包（`load_skill` 按需读） |
| 8 | 首期范围 | 四类全要：黑盒 Web/API、移动 App/小程序、内网/主机、白盒源码审计 |
| 9 | 分期 | **先平台后能力** |
| 10 | 用户模型 | **先单用户，预留多用户** |
| 11 | Strix 取舍 | **能力全保留**（MCP / CI / Cloud / benchmarks / tests） |
| 12 | XuanMu 取舍 | 保留 Blackboard + WorkProject + novnc；**砍本地 shell 模式** |
| 13 | 治理层 | **Strix 原有策略 + 用户可控的渗透策略控制台** |
| 14 | 产物落地 | **DB 为真源 + 镜像工作目录** `{workspace}\{任务}_SRC挖洞\` |
| 15 | 目标输入 | URL 清单 / 集团名 / 源码路径 / Apk·小程序·抓包 |
| 16 | 与旧文档 | **旧文档作废，本策划书重写** |
| 17 | LLM | **国产 API 为主**；**内置模型注册表（硬回退）**；用户只填 API Key；`/models` 拉取为 **best-effort**（国产 API 不保证暴露） |
| 18 | 出口网络 | **本机出口 + 低频低感知**；预留代理池接口 |
| 19 | 操作台 | 实时日志流 + 资产/攻击路径图 + 任务/队列面板 + **策略控制台** + **大模型思考链** |
| 20 | 外部对接 | 系统 Chrome + Yakit/Burp 抓包 + **通用 MCP 自适应**（FOFA/SRC 平台本期未选） |
| 21 | 一期验收 | **壳先跑通** |
| 22 | 复核机制 | **报告人工复核** + **知识库自增长（门槛+三问）后复核入库** |
| 23 | 授权与审计 | **强制授权范围 + 全量审计** |
| 24 | 批量调度 | 批量队列 + 定时周期 + 单目标手动 |
| 25 | 开发节奏 | **个人、无硬工期** |
| 26 | fork 时机 | **先完成本文档，再 fork** |
| 27 | 红线集合 | **DoS 绝对禁止** + **写 / 删 / 改 操作全部需用户确认** + **CORS 不挖**；禁测清单不继承（改由策略控制台按任务声明） |
| 28 | 补充 | 无 |

---

## 三、总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  交互层   React 操作台（XuanMu）           CLI（Strix 风格）            │
│           · 实时日志流 / 大模型思考链                                   │
│           · 资产·攻击路径图（Blackboard + WorkProject）                  │
│           · 任务/队列/种子面板                                          │
│           · ★渗透策略控制台（红线/允许动作/限速/范围）                    │
├──────────────────────────────────────────────────────────────────────┤
│  平台层（fork XuanMu）                                                 │
│   FastAPI 控制面 · PostgreSQL · WS 事件总线 · AgentSessionPool          │
│   会话/项目/权限(单用户起步) · WorkProject 记录 · Blackboard 推理图      │
├──────────────────────────────────────────────────────────────────────┤
│  流程层（引入 Strix）                                                  │
│   动态派生 agent（root → create_agent 子 agent，mailbox 回收）          │
│   工具层：Caido 抓包/重放 · Kali 工具链 · 系统 Chrome · MCP 自适应      │
│   报告管线：SARIF / CVSS / LLM 去重 / 预算控制                          │
├──────────────────────────────────────────────────────────────────────┤
│  方法论层（src-hunt 双轨）                                             │
│   ① 阶段骨架（硬编排）：判模式 → 一种子闭环 → 进站 §4 → 矩阵 → 闸门 → 报告 │
│   ② 技能包（软注入）：62 篇模块 + 打穿短表，按需 load_skill             │
├──────────────────────────────────────────────────────────────────────┤
│  治理层（自有）                                                        │
│   强制授权范围闸 · 渗透策略控制台（三层：task > profile > 不可关安全网） │
│   红线裁决（DoS 绝对 / 写删改需确认 / CORS 不挖）· 全量审计落库          │
├──────────────────────────────────────────────────────────────────────┤
│  执行沙箱（Docker，控制面=Strix Python）                              │
│   Kali 工具链 + Caido 强制代理 + novnc + 出口/低频（策略插件）         │
├──────────────────────────────────────────────────────────────────────┤
│  模型层  国产 API 为主 · 内置注册表(硬回退) · /models best-effort · 路由/预算 │
└──────────────────────────────────────────────────────────────────────┘
```

**核心数据流（一次任务）**：
```
操作台投喂目标 → 平台层建 Task(强制范围) → 流程层 root agent 启动
  → 阶段骨架驱动（判模式 → 清洗/种子 → 进站） 
  → 需要能力时：load_skill 注入 src-hunt 模块 / 动态派生子 agent / 沙箱 exec
  → 差分验证 → finding（过三闸）
  → 报告：中文 03（人工复核后定稿）+ SARIF/CVSS
  → 落 PG + 镜像 {workspace}\{任务}_SRC挖洞\ + 审计入库
```

---

## 四、平台层改造（fork XuanMu）

**保留**：`app.py`/`config.py`/`database.py` 控制面；`core/runtime/session.py` 会话池；`core/conversation/` 记忆与压缩；`core/tools/blackboard.py`、`core/tools/work_project_records.py`；`sandbox/` 镜像与 Go 控制面；`web/` React 操作台。

**改造**：
1. **角色体系**：`core/agent/specs.py` 的静态 `AGENT_SPECS`（cso + 5 专家）→ 改为**动态派生**（借 Strix `tools/agents_graph/tools.py` + `core/execution.py:spawn_child_agent` 的 mailbox 模型）。
2. **砍 `core/tools/local_shell.py`**：所有命令**强制走沙箱**（安全）。
3. **策略控制台**：新增配置面与管理 API（见 §七）。
4. **授权范围闸**：Task 创建时强制绑定范围（域名/资产清单 + 有效期），越界即拒。
5. 单用户起步，保留用户/项目表结构以预留多用户。

**关键锚点**：`app.py:101/124`、`core/agent/specs.py:103`、`core/agent/registry.py:130`、`core/runtime/session.py:95/256`、`service/agent/runtime.py:90`、`service/sandbox/commands.py:344`、`sandbox/proxy/main.go:51`。

---

## 五、流程层（引入 Strix）

**全量保留** Strix 能力，作为 ravenholt 的**渗透执行引擎**接入：
- **动态派生**：`core/agents.py:56 AgentCoordinator`（状态/mailbox/wake）+ `core/execution.py:386 spawn_child_agent` + `agents/factory.py:663 build_strix_agent`。
- **工具**：`tools/proxy`(Caido GraphQL：抓包/重放/scope)、`tools/reporting`、`tools/agents_graph`、`tools/load_skill`、`tools/mcp/*`、terminal(SDK Shell)。
- **沙箱运行时**：`runtime/backends.py`(注册表) + `runtime/session_manager.py:258 create_or_reuse` + `runtime/docker_client.py:164`（资源限额）。
- **报告管线**：`report/state.py` + `report/writer.py` + `report/sarif.py`(CVSS/STRIDE) + `report/dedupe.py`(LLM 去重)。
- **LLM/预算**：`config/models.py:552 StrixProvider`(LiteLLM) + `core/hooks.py:152 ReportUsageHooks` + `--max-budget`。
- **保留** MCP 自适应、CI/GitHub Actions、Cloud 模式、`benchmarks/`、`tests/`。

**与平台层的接缝**：把 Strix 的 agent 运行时作为 XuanMu `AgentSession` 的**执行后端**；Strix 的 findings 写入 XuanMu 的 WorkProject（Asset/Finding/AttackPath），事件并入 XuanMu WS 时间线（这样操作台能画攻击路径图）。

---

## 六、方法论层（src-hunt 双轨）

**① 阶段骨架（硬编排，保证纪律落地）**：
```
判模式（锁面 / 自由跳）
自由跳：种子尽能力多备 → 落盘队列 → 一种子闭环（搜一个 → 去重去废去非存活 → 股权闸 → 挖完 → 才搜下一个）
锁面：  资产簇多 host / 业务流子域 / 同 host 多 path
单站：  说清这摊 → 指纹(先证伪) → 抽 JS 钥匙 → 建清单 → 全类型矩阵 → 同闸停 → 落报告 → 换站
闸门：  空转自纠（15~20min 无苗头换线）· 深挖优先（本种子未挖完不搜下一个）
```

**② 技能包（软注入）**：62 篇模块 + `打穿短表.md` 放入沙箱 `skills/`，用 `load_skill` **按需读整篇**（照 Strix 做法，不做向量 RAG）；`打穿短表` 作为**开场几枪强制索引**。

**报告口径**：正文严格按 src-hunt `03` 中文 7 段（匿名闸/认钥闸/别重复交）；同时产出 SARIF/CVSS。

---

## 七、治理层（自有，用户可控）

- **基础**：沿用 Strix 原有权限/策略模型。
- **新增：渗透策略控制台**（操作台页面 + 后端配置）：
  - 三层覆盖：`task 级 > profile 级 > 不可关安全网`
  - **不可关安全网**（tier-1）：限速机制本身、Kill Switch、沙箱资源上限、审计落库
  - 可配：允许动作分级、需同意动作、DoS 定义、限速参数、**禁测清单（按任务声明）**
- **红线（默认，出厂）**：**DoS 绝对禁止**（无例外）；**写 / 删 / 改 三类操作一律需用户确认**（无论对目标还是对平台自身）；**CORS 不挖**。
  - **对目标**（改密/改绑/提交/上传落文件/下单/删除对象）：默认只读，**须确认**才执行。
  - **对整个平台自身**（agent 写工具 / 改配置或策略 / 删除文件或记录 / 改写工作目录产物）：同样**须确认**。
  - **★ 两种模式的行为（修正：不挂起、不卡死）**：
    - **无人值守 `mode=auto`（默认）**：写/删/改 = **自动拒绝（auto-deny）并记录，然后继续只读探测**。**不挂起、不等待**——否则会卡死在第一个写操作，与 M8"无人值守跑批"直接冲突。
    - **人在环 `mode=interactive`（任务级显式声明）**：写/删/改才**挂起进「待确认队列」**，操作台可批量批准/驳回。
  - **结论**：**无人值守 ≠ 什么都做**，而是"只读到底"；**确需写操作的任务，必须显式声明为 `mode=interactive`**。
  - 只读动作（探测 / 抓包 / 差分 / 读文件）不受此闸约束。
- **授权闸**：任务强制绑定授权范围 + 有效期，越界即拒。
- **★ 证据唯一来源（防 AI 幻觉 · 硬原则）**：**agent 的记忆 / 对话 / 思考链都不算证据**。任何「打穿了 / 存在漏洞」的结论，**必须由独立验证器重放 evidence（整包 + 差分）并复现**，才允许进入 `verified`；agent 自述 **100% 不采信**。
  - **验证器独立于 agent**：确定性重放同一请求 → 复现同一差分；**复现不出即证伪丢弃**（不是标"未验证"、更不是标"疑似"）。
  - **操作台思考链标注**：哪些是 agent 的**推测**（未验证）、哪些是**已验证事实**（有 evidence），一眼可辨。
  - **不跨会话保留**：agent 上下文/记忆里的"洞"随会话消失；**只有落了 evidence 的才作为 finding 留存**。
- **审计**：全量记录「谁 / 何时 / 对哪个目标 / 做了什么 / 裁决结果」，入库可查。

---

## 八、沙箱与运行环境

- **部署**：平台 / 前端 / PostgreSQL 跑在 **Windows 本机**；渗透执行跑在 **Docker 沙箱**（Windows 上经 Docker Desktop）。
- **镜像**：以 **Strix Kali 镜像**为底（预装 nmap/sqlmap/nuclei/ffuf/katana/httpx/semgrep/trivy…）+ Strix Caido 强制代理（:48080）+ XuanMu 的 **novnc 可视化**。
- **★ 控制面单一（修正）**：**只保留 Strix 的 Python 沙箱侧**（`runtime/docker_client.py` + `backends.py`，接口清晰、易扩展）；**不合并** XuanMu 的 Go 控制面（`sandbox/proxy/main.go`）——"合并镜像"容易，"合并两套控制面"是另一个项目。
- **出口控制改造为策略插件**：把 XuanMu 的**出口控制 / 低频低感知**（出口模式 + 限速 + 随机间隔 + 熔断）移植成 Strix 沙箱侧的**策略插件**，而非并行控制面。
- **出口**：默认**本机出口 + 低频低感知**（单主机 ≤10 次/分钟），**预留代理池接口**（HTTP/SOCKS）。
- **隔离**：文件/网络容器隔离；命令只经沙箱；**无本地 shell 逃逸路径**。

---

## 九、数据与产物

- **真源**：PostgreSQL（继承 XuanMu `agent_sessions/agent_messages/...` + 新增）：`targets` / `seeds` / `endpoints` / `findings` / `evidence` / `verifier_runs` / `reports` / `policy_profiles` / `audits` / `tasks`。
- **★ evidence 是一等公民（修正）**：独立落库，**与 agent transcript（对话/思考链）物理分离**。
  - `evidence` = `{ raw_request, raw_response, diff(四维：状态码/长度/内容/业务码), verifier_result, oob_log? }`
  - `verifier_runs` = 验证器每次重放的独立记录（时间 / 命中差分 / 结论 `reproduced | refuted`）
  - **`findings` 必带 `evidence_id` 外键**；**无 `evidence_id` 的 finding 只能是 `draft`**
  - 操作台「推测 vs 已验证」标注**从 `finding.evidence_id` 是否存在读取**（数据模型驱动，不是前端临时判断）
- **镜像产物**：`{workspace}\{任务}_SRC挖洞\`（`资产/ js/ 报告/ {名}_dig/`）+ `{workspace}\tools\`、`{workspace}\tmp\`。
- **报告**：中文 `.md`（文件名=标题，CRLF）+ `vulnerabilities.json` + `findings.sarif` + `run.json`。
- **finding 生命周期（硬）**：`draft → verified → reported`；**进入 `verified` 的必要条件 = 存在可重放 evidence（整包 + 差分）且独立验证器复现成功**；**agent 自述 / 思考链 / 记忆 均不构成证据**。

---

## 十、模型层

- **国产 API 为主**（DeepSeek / Qwen / GLM 等），兼容 XuanMu 的 per-agent 独立 `base_url/api_key/model`。
- **内置模型注册表（硬回退，必装）**；用户只填 API Key；**`/models` 自动拉取为 best-effort**——国产 API（DeepSeek/Qwen/GLM）的 `/models` 端点**不保证暴露**（与网关配置相关，有的根本没有），**拉不到就回退内置注册表**，并在 UI 标注"未发现新模型"。
- **路由与预算**：主控/写报告用强模型，批量抽取/汇总用便宜模型；沿用 Strix 的用量钩子与预算上限。

---

## 十一、界面

操作台五大件：**实时日志流** · **大模型思考链**（同 XuanMu） · **资产/攻击路径图**（Blackboard + WorkProject，cytoscape） · **任务/队列/种子面板** · **渗透策略控制台**。另有 CLI（Strix 风格，headless/批量用）。

---

## 十二、输入、批量与复核

- **目标输入**：URL 清单 / 集团名 / 源码路径 / Apk·小程序·抓包（四类）。
- **调度**：批量目标队列（保守并发 2~3）+ 定时周期任务（cron）+ 单目标手动。
- **复核**：**报告草稿 → 人工复核 → 定稿落盘**；**知识自增长**（按 src-hunt `04` 门槛+三问生成「拟进/拟补」候选 → 人工复核 → 写入短表/模块）。
- **验证前置（防幻觉）**：复核队列**只接受 `verified`（evidence 已重放复现）的 finding**；仅 agent 自述、无 evidence 的 `draft` **不进复核队列、不落盘、不进报告**。

---

## 十三、里程碑

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| **M0 基线** | fork XuanMu 进 ravenholt（保留 git 历史）；建目录、跑通依赖 | 仓库就位 |
| **M1 壳跑通（一期验收）** | PG + React 操作台 + WS + 建会话/看思考链/看流；渗透能力可先空壳 | **能在本机打开操作台并发起一个会话** |
| **M2 流程引擎接入** | 接 Strix agent 运行时 + Docker 沙箱（Strix Kali 镜像，**单一控制面**）+ 工具层 + **evidence 存储 + 独立验证器骨架（重放 + 四维差分）** | 能跑通占位渗透流程；验证器能对样例 evidence 复现/证伪 |
| **M3 单一垂直闭环（只做黑盒 Web/API）** | **端到端跑通一个目标**：src-hunt 阶段骨架 + 技能包 + 差分 → **过证据闸（finding 只认 `verified`）** → 中文 03 报告 + SARIF + 审计。**移动/白盒/内网一律后移**，本里程碑不铺 | 单目标出合规报告；**每个 finding 都能重放复现** |
| **M4 策略控制台 + 审计 + 授权闸** | 治理层落地 | 越界即拒、审计可查、红线可配 |
| **M5 移动 App/小程序** | jadx/apktool + 抓包/小程序专项（含 src-hunt 小程序 token 流程） | 能出移动侧发现 |
| **M6 白盒源码审计** | src-hunt Phase0~6 接入 | 能审一份源码出发现 |
| **M7 内网/主机** | nmap 内网侧 | 内网资产与发现 |
| **M8 批量/定时/CLI/CI** | 批量队列、cron、CLI headless、GitHub Actions | 无人值守跑批 |

---

## 十四、风险与对策

| 风险 | 对策 |
|------|------|
| **两套 agent 运行时接缝复杂**（XuanMu session vs Strix coordinator） | 先做 M2 的"最小接缝"验证，别先改平台内部 |
| 无人值守误伤目标 | 强制授权范围 + 策略控制台 + tier-1 不可关安全网 + Kill Switch |
| Docker 依赖（Windows Desktop） | 明确为前置条件；保留"平台可脱离沙箱空跑"以利调试 |
| 上游快速迭代导致 fork 漂移 | 尽量不动上游文件、改造集中在少数适配层 |
| 四类范围同时铺导致失焦 | 严格执行"先平台后能力"分期 |
| LLM 幻觉/误报 | 差分硬证据 + 报告人工复核 + 三闸 |
| 知识库被污染 | 自增长候选**人工复核后**才入库 |
| 许可合规 | 保留 MIT/Apache-2.0 声明与 NOTICE |

---

## 十五、开放项（后续再定）

1. M0 fork 时是否**保留完整 git 历史**（clone）还是浅克隆。
2. 策略控制台的**配置存储**：入库（PG）为主 + 导出 YAML？
3. CLI 与操作台的能力边界（哪些必须 CLI-only）。
4. 白盒/移动期的**专用沙箱镜像**是否独立。
5. 是否需要"多目标差异报告"（定时任务的环比）。
6. `{workspace}` 默认位置与命名约定。

---

## 十六、参考锚点（便于落地时直接定位）

- XuanMu：`app.py:101/124`、`config.py:91`、`core/agent/specs.py:103`、`core/agent/registry.py:130`、`core/runtime/session.py:95/256`、`core/delegation/subagents.py:105`、`service/agent/runtime.py:90`、`service/sandbox/commands.py:344`、`sandbox/proxy/main.go:51`。
- Strix：`interface/main.py:429`、`core/agents.py:56`、`core/execution.py:386`、`core/hooks.py:152`、`agents/factory.py:663`、`runtime/session_manager.py:258`、`runtime/docker_client.py:164`、`report/state.py`、`report/sarif.py:336`、`config/models.py:552`。
- src-hunt：`SKILL.md` §2/§4、`references/01~10`、`知识库/`62 篇 + 打穿短表。
