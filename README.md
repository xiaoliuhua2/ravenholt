<div align="center">

<img src="docs/public/ravenholt-logo.png" alt="Ravenholt" width="120" />

# Ravenholt · 红队智能体协作平台

> 面向**授权**渗透测试、漏洞挖掘、代码审计与安全研究的开源红队多智能体协作平台

<a href="https://github.com/xiaoliuhua2/ravenholt"><img src="https://img.shields.io/badge/Release-v0.2.1-blue" alt="Version"></a>
<a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
<a href="https://xiaoliuhua2.github.io/ravenholt/"><img src="https://img.shields.io/badge/Docs-online-2ea44f" alt="Docs"></a>
<a href="./CHANGELOG.md"><img src="https://img.shields.io/badge/Changelog-CHANGELOG.md-6f42c1" alt="Changelog"></a>

<br/>

<img src="docs/public/images/landing.png" alt="Ravenholt 落地页" width="880" />

**中文** · [English](./README.en.md) · [在线文档](https://xiaoliuhua2.github.io/ravenholt/)

</div>

---

> [!WARNING]
> **仅限授权使用。** 本项目只允许在**合法且已获得明确书面授权**的范围内用于安全测试、风险评估、代码审计与研究。
> 它不会、也不应被用于访问或影响任何未授权的第三方系统、网络、服务、账户或数据。未经授权进行测试在多数司法辖区属违法行为。
> **作者不对任何误用及由此产生的后果承担责任。**

---

## 目录

1. [项目简介](#一项目简介)
2. [功能特性](#二功能特性)
3. [技术架构](#三技术架构)
4. [环境要求与全部依赖](#四环境要求与全部依赖)
5. [下载与安装部署](#五下载与安装部署)
6. [配置说明](#六配置说明)
7. [启动与运维](#七启动与运维)
8. [快速上手](#八快速上手)
9. [界面一览](#九界面一览)
10. [目录结构](#十目录结构)
11. [常见问题](#十一常见问题)
12. [许可](#十二许可)

---

## 一、项目简介

Ravenholt 是**以控制平面为中心**的红队多智能体平台：把 agent 辅助的安全工作做成**可管控、可复核**的工程流程 —— 会话不是唯一的事实来源，项目范围、资产、发现、关系图、攻击路径、可回放时间线，以及 agent 的推理过程，都会作为显式数据被持久化。

底层以 [strix](https://github.com/usestrix/strix) 作为渗透执行引擎（已 vendor 进本仓库，见 `.strix-vendor.json`），并在其上叠加平台控制面、策略治理层与证据面：

| 组成 | 作用 |
| --- | --- |
| **strix 运行时**（vendor） | 渗透/审计执行引擎：agent 编排、技能库（skills）、沙箱工具链、Caido 抓包、报告 |
| **平台控制面**（本仓库） | 会话 / 项目 / 用户 / 主机 / 系统配置的统一入口，REST + WebSocket，权限与资源边界 |
| **策略治理与证据面** | 红线策略（fail-closed）、动作审批、审计日志、WorkProject 证据、可回放时间线 |
| **一体化沙箱镜像** | 本仓库 `sandbox/` 构建的 `sandbox-runtime:latest`：上游能力（Caido + Kali 工具链）+ 定制工具集（Ghidra / Jadx / observer_ward / agent-browser）+ 容器内控制面与技能资源 |

### 1.1 与上游 strix 的关系与区别

**关系：strix 是本项目的执行引擎，不是竞品。** strix 源码已整份 vendor 进 `strix/` 目录（431 个文件），平台**不改造它的包内运行时逻辑**——设计约束是「只做装配与适配」，以便随时跟随上游升级。`.strix-vendor.json` 记录上游仓库地址、commit、每个文件的 SHA-256 与受保护前缀（`skills/src_hunt/`），供校验与对齐使用。

**一句话区别：** strix 是「单机 CLI / TUI 渗透 agent」；ravenholt 是「以控制平面为中心的红队多智能体协作平台」——同一套 agent 运行时，被放进带会话、项目、证据、策略与审计的工程流程里。

| 维度 | 上游 strix | ravenholt（本项目） |
| --- | --- | --- |
| 交互形态 | 命令行 / 终端 TUI / 自带 viewer（读本地 run 目录） | Web 控制台（REST + WebSocket）：会话、项目、策略、审计、容器控制台 |
| 执行引擎 | 自带 agent 运行时、skills、沙箱、Caido | **复用**（vendor 同一套），平台只在装配层注入模型配置与运行上下文 |
| 模型接入 | strix 自己的 settings / LiteLLM 解析 | 平台 per-agent 配置（`agents` 段）注入，不改 strix 内部逻辑 |
| 会话 | 一次 run（单次扫描） | 多会话：中断 / 取消 / 恢复、会话池、后台子智能体任务与唤醒 |
| 编排 | 进程内 root agent 派生 | 平台侧 `AgentCoordinator` + 邮箱回收 + 可视图（子代理完成报告回投父代理） |
| 过程沉淀 | 报告文件（markdown / SARIF） | **WorkProject**：范围资产、发现、关系图、攻击路径、可回放时间线 |
| 证据 | agent 自述即结论 | **差分级证据 + 独立验证器**：平台重放 baseline / probe，`reproduced` 才允许离开草稿态 |
| 治理 | 无 | **红线策略（fail-closed）+ 审批队列 + 审计日志 + 出口代理** |
| 沙箱 | 上游镜像（Caido + Kali 工具链） | 同一基础镜像叠加逆向工具、容器内 Go 控制面、桌面栈、容器内技能资源 |
| 联网检索 | Exa / Perplexity | 扩展**本机 SearXNG（零配置）与 DeepSeek**；`auto` 按可用性排序并在失败时降级 |
| 技能 | 上游 skills 库 | 同一加载器 + 镜像技能注册 + **确定性技能路由**（`route_skills`） |
| 增量位置 | — | `core/` `service/` `router/` `schema/` `model/` `web/` `sandbox/`；`strix/` 保持上游原样 |

> 两者可以并存：`strix/` 既是引擎源码，也是升级时的对齐基线（`scripts/verify_strix_version_alignment.py`）。

---

## 二、功能特性

### 2.1 功能与前置条件对照表

下表把每个功能「需要什么、在哪里开启」一次说清。按「[8.2 启用完整功能](#82-启用完整功能)」的顺序执行即可把全部能力打开。

| 功能 | 需要什么 | 怎么开启 |
| --- | --- | --- |
| 登录、用户与角色、系统配置 | PostgreSQL + 配置文件 | `bash setup.sh` 自动完成 |
| 操作台会话（与 agent 流式对话） | **LLM API Key**（OpenAI 兼容端点） | 系统配置页填写，或 `bash config-tool.sh set ...` |
| 会话中的**渗透/审计执行**（沙箱） | Docker + 沙箱镜像 | 首次会话自动拉取上游镜像（约 4 GB）；构建一体化镜像后会话改用定制工具集 |
| 平台「沙箱容器」控制台<br/>（终端 / 文件管理 / noVNC 远程画面） | `sandbox-runtime:latest` + 镜像记录 | `cd sandbox && bash build.sh`，再到「沙箱镜像」页登记（Control Port 填 `8000`） |
| Caido 抓包 / 重放 / 请求库 | 沙箱执行面（两种镜像都自带） | 随会话自动启动，无需配置 |
| 二进制逆向（Ghidra / Jadx / apktool / binwalk） | 一体化镜像 | 构建 `sandbox-runtime:latest` 后自动对会话生效 |
| 浏览器自动化（agent-browser-cli） | 一体化镜像 | 同上 |
| 联网检索（`web_search` / `web_get_contents`） | 本机 SearXNG **或** Exa / Perplexity Key | **零配置**：平台启动时自动拉起本机 SearXNG 容器；也可填第三方 Key |
| 出口代理（受控网络出口） | 一体化镜像（容器内控制面）+ 代理条目 | 构建镜像，再到「出口代理」页配置链路 |
| OOB 外带回连（反弹 shell 收口） | macvlan 网络（宿主需支持） | `bash serve.sh start` 自动执行 `sandbox/setup_macvlan.sh`；不支持时回退 bridge |
| 工作项目 / 资产 / 发现 / 关系图 / 攻击路径 | 控制面基础 | 开箱可用 |
| 源码审计通道（白盒分轨） | LLM Key + 源码包 | 项目内上传源码包后自动切换技能路由与提示词 |
| 策略审批（高风险动作挂起待批） | `.ravenholt/policy.yaml` | `setup.sh` 自动生成；控制台可即时调整 |
| 审计日志 | `policy.yaml` 的 `audit.enabled=true` | 默认开启（Tier-1，不可关闭） |
| 可回放时间线 | 控制面基础 | 开箱可用 |
| 全量事件归档（旁路落盘） | `config.json` 的 `archive` 段 | 默认开启 |
| MCP 工具接入 | MCP 服务配置 | 会话内按需加载 |

> 一句话：**核心必需 = Python 3.12+ / PostgreSQL / 一个 LLM API Key**；**完整功能 = 再加 Docker 与一体化沙箱镜像**。

### 2.2 功能明细

- **操作台（Playground）**：多智能体会话、流式对话、子智能体面板、思考过程内联展示、可回放时间线；会话列可拖拽调宽、可一键收起。
- **沙箱执行面**：Docker 沙箱容器提供 Kali 工具链、终端、文件管理、noVNC 远程画面与 Caido 抓包/重放；按会话自动 provision。
- **工作项目（WorkProject）**：项目元数据、负责人、范围资产、会话、记录、关系图与攻击路径；发现携带证据与影响。
- **源码审计通道（白盒）**：上传源码包后可走白盒分轨，技能路由与提示词随之切换。
- **出口代理**：受控网络出口的配置与管理（代理出口链路）。
- **策略审批**：红线策略判定动作是否放行；高风险动作进入审批队列，由管理员批准/拒绝。
- **审计日志**：关键动作与事件的审计追踪（动作、判定、拦截原因等）。
- **系统用户 / 系统配置**：账号与角色权限、运行参数与集成配置。
- **可回放时间线**：所有来源按时间归并为唯一顺序视图，支持事后逐条复核。

---

## 三、技术架构

```
┌──────────────────────────────────────────────┐
│  前端控制台（React 19 + Semi UI + Vite）      │
│  Landing · Login · 操作台 · 工作项目 · 审计…  │
└───────────────────────┬──────────────────────┘
                        │ REST + WebSocket
┌───────────────────────▼──────────────────────┐
│  控制平面（FastAPI，/api）                    │
│  用户 · 会话 · 项目 · 策略 · 审计 · 配置       │
└───────┬───────────────────────┬──────────────┘
        │                       │
┌───────▼────────┐      ┌───────▼──────────────┐
│ 会话运行时      │      │ 证据面（WorkProject） │
│ strix 引擎      │      │ 资产/发现/关系图/路径 │
│ 动态派生 agent  │      │ 证据链 + 验证器       │
└───────┬────────┘      └──────────────────────┘
        │
┌───────▼──────────────────────────────────────┐
│  沙箱执行面（Docker，一体化镜像）             │
│  Caido · Kali 工具链 · Ghidra/Jadx · noVNC    │
└───────┬──────────────────────────────────────┘
        │
┌───────▼──────────┐
│  PostgreSQL 16   │
└──────────────────┘
```

| 层 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite 8、Semi UI、CodeMirror、xterm、Cytoscape、Mermaid |
| 后端 | Python 3.13、FastAPI、SQLModel/SQLAlchemy、asyncpg、Uvicorn、WebSocket |
| 执行引擎 | strix（vendor）、Docker 沙箱、Caido、Kali 工具链 |
| 沙箱镜像 | `sandbox/build.sh` → `sandbox-runtime:latest`（基于上游 strix 镜像叠加定制能力） |
| 数据库 | PostgreSQL 16 |
| 部署 | venv 直跑 / Docker Compose |

### 沙箱执行面：一个镜像，两种用途

平台的沙箱由两个环节共同决定，理解它们就能理解全部沙箱行为：

| 环节 | 谁负责 | 用什么 |
| --- | --- | --- |
| **容器内有什么** | 镜像 | 默认 `ghcr.io/usestrix/strix-sandbox:1.3.0`（上游，含 Caido + Kali 工具链）；构建后改为 `sandbox-runtime:latest`（一体化） |
| **容器由谁创建、怎么执行命令** | 平台 | 会话容器由 strix SDK 按需拉起；命令经 [service/sandbox/commands.py](service/sandbox/commands.py) 以 Docker `exec` 执行，**不依赖容器内的控制面** |

两种镜像的能力对比：

| 能力 | 上游 `strix-sandbox:1.3.0` | 一体化 `sandbox-runtime:latest` |
| --- | --- | --- |
| Caido 抓包 / 请求库 / 重放 | ✅ | ✅ |
| Kali 工具链（nmap / sqlmap / nuclei / ffuf / katana / httpx / semgrep / trivy / chromium / node / python / uv） | ✅ | ✅ |
| Ghidra / Jadx / apktool / binwalk | ❌ | ✅ |
| observer_ward / agent-browser-cli | ❌ | ✅ |
| 容器内 Go 控制面（终端 / 文件 / noVNC / egress 动态刷新） | ❌ | ✅ |
| 容器内技能资源 `.agents/skills` | ❌ | ✅ |
| 桌面栈 Xvfb + x11vnc + noVNC、tor | ❌ | ✅ |

**一体化镜像的做法**：`sandbox/Dockerfile` 以 `ghcr.io/usestrix/strix-sandbox:1.3.0` 为**基础镜像**（`FROM ${STRIX_SANDBOX_IMAGE}`），在其上叠加上述增量，并沿用上游的 `ENTRYPOINT`（由 `/ravenholt-entrypoint.sh` 先把附加服务挂到后台，再 `exec` 上游脚本启动 Caido），因此不会丢掉上游任何能力。

- **不构建**：会话用上游镜像即可做渗透（含抓包），只是缺少 Ghidra/Jadx 等定制工具与平台容器控制台。
- **构建后**：`setup.sh --with-sandbox` 会把镜像名自动写进 `config.json` 的 `sandbox.image`，会话与平台容器**都用**一体化镜像。
- 手工部署时，只需在 `.ravenholt/config.json` 里填 `"sandbox": { "image": "sandbox-runtime:latest" }`（见 [6.1](#61-ravenholtconfigjson)）。

---

## 四、环境要求与全部依赖

> 首次部署请从 4.1 装到 4.4；只想要「能登录 + 能对话」的最小形态，装 4.1 就够。

### 4.1 核心必需（缺一不可）

| 项目 | 要求 | 校验命令 |
| --- | --- | --- |
| 操作系统 | **Linux x64**（推荐 Kali Rolling / Debian） | `uname -m` |
| Python | **≥ 3.12**（推荐 3.13），含 `venv` | `python3 -V` |
| PostgreSQL | **16+** 且服务已启动 | `psql --version`、`pg_isready` |
| LLM API Key | OpenAI 兼容端点（DeepSeek / OpenAI / 自建均可） | — |
| 网络 | 可访问 PyPI 与 npm 镜像、LLM 端点 | `curl -I https://pypi.org` |
| 磁盘 | ≥ 2 GB（平台本体 + 前端产物） | `df -h .` |

### 4.2 完整功能依赖（按功能展开）

| 组件 | 版本/规格 | 提供的能力 | 不装的后果 |
| --- | --- | --- | --- |
| **Docker** | 24+，daemon 已运行 | 沙箱执行面（会话中的命令执行、Caido 抓包） | 只能使用控制面，无法做渗透 |
| **一体化沙箱镜像** | `sandbox-runtime:latest`（构建约 5 GB+） | Ghidra/Jadx/apktool/binwalk/observer_ward/agent-browser、容器控制台、egress 运行时刷新、技能资源 | 会话仍可用上游镜像跑渗透，但缺上述定制工具与控制台 |
| **上游沙箱镜像** | `ghcr.io/usestrix/strix-sandbox:1.3.0`（约 4 GB） | Caido + Kali 工具链 | 首次会话会自动拉取；离线环境需预拉 |
| **Node.js** | ≥ 20.19（推荐 22） | **构建前端（源码部署必需）**：仓库不含 `web/dist-app`，须 `npm install && npm run build` 生成 | 不装则控制台页面无法加载；但不必手工处理——`setup.sh` 会**自动安装**（官方二进制 22.x 解压到 `/usr/local`）；Docker/Compose 部署由镜像内构建阶段完成，不需要宿主 Node |
| **Docker Compose** | v2 | Compose 部署方式 | 只用 `serve.sh` 则无影响 |
| **SearXNG 容器** | `searxng/searxng:latest`（约 265 MB） | 零配置联网检索 | 平台会自动拉起；离线环境需改配 Exa/Perplexity Key |
| **macvlan 支持** | 宿主网卡允许 L2 多 MAC | 目标主动回连（OOB 外带 / 反弹 shell 收口） | 自动回退 bridge，OOB 走容器内 interactsh |
| **JRE** | 由一体化镜像内置（`openjdk-21-jdk-headless`） | Ghidra / Jadx 运行 | 使用一体化镜像时无需自装 |

### 4.3 系统包清单

一键脚本（`setup.sh`）会自动安装下列内容；手动部署请照此安装。其中 **Node.js 走官方二进制**（解压到 `/usr/local`，避开发行版仓库的老版本）、**Docker 走发行版包并自动启动守护进程**。

| 用途 | 包 |
| --- | --- |
| 运行平台 | `python3`、`python3-venv`、`python3-pip` |
| 数据库 | `postgresql`、`postgresql-client` |
| 基础工具 | `curl`、`openssl`、`ca-certificates`、`git` |
| 沙箱运行时 | `docker.io`（+ `systemctl enable --now docker`） |
| 前端构建 | Node.js 22.x 官方二进制（脚本自动下载到 `/usr/local`；可用 `NODE_MIRROR` / `NODE_VERSION` 覆盖源与版本） |

> 一体化沙箱镜像所需的系统包（apktool、binwalk、7zip、make、sqlite3、openjdk-21-jdk-headless、xvfb、x11vnc、novnc、websockify、tor、supervisor 等）在 `sandbox/Dockerfile` 里声明，由 `docker build` 自动安装，**不需要**在宿主上安装。

### 4.4 Python 与前端依赖

| 来源 | 内容 |
| --- | --- |
| `requirements.txt` | 后端全部依赖（FastAPI、SQLModel、asyncpg、docker、openai-agents[litellm]、caido-sdk-client、jinja2、pydantic 等） |
| `web/package.json` | 前端依赖（React 19、Semi UI、Vite 8、CodeMirror、xterm、Cytoscape、Mermaid 等），仅重新构建前端时安装 |

### 4.5 端口清单

| 端口 | 用途 | 默认绑定 |
| --- | --- | --- |
| `8000` | 控制面 HTTP + WebSocket；**沙箱容器内** Go 控制面也监听 8000 | `0.0.0.0`（宿主）/ 容器内 |
| `5432` | PostgreSQL | `127.0.0.1`（Compose 下发布到宿主） |
| `8888` | 本机 SearXNG（联网检索后端） | `0.0.0.0`，可用 `searxng_bind_addr` 收窄 |
| `5433` | pgAdmin（仅 Compose 编排） | `0.0.0.0` |
| `30000–60999` | 平台沙箱容器的控制代理（动态分配） | 按需 |
| `48080` | 沙箱容器内 Caido 代理 | 容器内 |
| `5900` / `8080` | 沙箱容器内 x11vnc / noVNC（一体化镜像） | 容器内 |

> 部署在**公网可直达**的主机上时，请收窄 SearXNG 的监听地址（见 [6.5](#65-联网检索配置)），并考虑用防火墙或反向代理限制控制面访问。

---

## 五、下载与安装部署

### 5.1 下载源码

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git
cd ravenholt
```

> 也可以直接下载 ZIP 解压。仓库已 vendor 完整的 `strix/` 运行时（431 个文件），**但前端构建产物 `web/dist-app` 不入库**：源码部署必须先构建一次前端（见 [5.3](#53-手动分步部署) 第 5 步，需 Node ≥ 20.19）；用 Docker / Compose 部署则由镜像构建阶段自动生成。
>
> **不想装 Node、不想本地构建前端**：直接下载 Release 附件 `web-dist-app.tar.gz`（由 CI 在打 tag 时构建，见 [`.github/workflows/build-frontend.yml`](.github/workflows/build-frontend.yml)）解压即可，跳过 [5.3](#53-手动分步部署) 第 5 步：
>
> ```bash
> wget https://github.com/xiaoliuhua2/ravenholt/releases/latest/download/web-dist-app.tar.gz
> tar -xzf web-dist-app.tar.gz -C web/      # 解压出 web/dist-app
> ```

### 5.2 一键部署（完整功能，推荐）

```bash
# 1) 先体检：只检测环境，不改动任何文件
bash setup.sh --check

# 2) 完整部署：检测 → 装系统依赖 → 初始化配置 → 建库
#    → 装 Python 依赖 → 构建前端 → 构建一体化沙箱镜像 → 自检
#    （--with-sandbox 会额外构建 sandbox-runtime:latest，即完整功能所需）
bash setup.sh --with-sandbox

# 3) 只想先把运行环境备好（自动装 Node.js / Docker），其余步骤稍后再做：
bash setup.sh --deps-only     # 装完系统依赖即退出
bash setup.sh --no-deps       # 反向：不自动装系统依赖与 Node.js / Docker
```

脚本共 8 段，逐段打印结果：

| 段 | 内容 |
| --- | --- |
| 1/8 环境检测 | 系统/架构/Python/Node/Docker/PostgreSQL/权限/端口/磁盘，逐项给出结论与修复命令 |
| 2/8 系统依赖 | 缺什么装什么（apt）；**并自动安装 Node.js（官方二进制 22.x）与 Docker（安装 + 启动守护进程）**；开头会**并发测速挑选最快的镜像源**（PyPI / npm / Node / apt），装完复检 Python/venv 等硬性依赖 |
| 3/8 配置初始化 | 生成 `.ravenholt/config.json`（随机 `encrypt_key`、数据库口令、管理员口令）与 **`policy.yaml`** |
| 4/8 PostgreSQL | 启动服务、建角色与数据库，口令与 config.json 对齐 |
| 5/8 Python 依赖 | 建 `.venv` 并 `pip install -r requirements.txt` |
| 6/8 前端构建 | `web/` 下 `npm install --include=optional` + `npm run build`，产出 `web/dist-app`；若因缺少可选原生依赖（Vite 8 的 rolldown 平台绑定）失败，**两步自愈**：①补装可选依赖后重试；②仍失败则从报错中解析缺失的绑定名，按 rolldown 实际版本显式安装 `@rolldown/binding-<平台>` 再重试（实测仅 `--include=optional` 往往补不回，第 ② 步才生效） |
| 7/8 沙箱镜像 | 检测上游镜像是否已拉取；**先尝试拉取 CI 已构建好的 GHCR 镜像（几分钟，免本地构建）**，拉不到再按 `--with-sandbox` 本地构建；**成功（拉取或构建）都会自动把 `sandbox.image` 写入 config.json** |
| 8/8 安装后自检 | 语法编译、config/policy 加载、`create_app` 装配冒烟 |

脚本**幂等**：已存在的 `config.json` / `policy.yaml` 不会被覆盖；`sandbox.image` 已有值时不会被改写。已存在 `web/dist-app` 时会**跳过前端构建**（省下每次重跑的构建时间），需要重建时加 `--rebuild-frontend`。

升级到新版本用 [`update.sh`](#七启动与运维)：`bash update.sh` = `git pull` → 更新依赖 → 必要时重建前端 → 重启服务。

> [!TIP]
> **所有下载与长任务都会打印实时进度，不会静默卡住**：apt（`Get` / `Setting up` 行）、Node.js 二进制（curl 自带进度条：百分比 / 速率 / 剩余时间）、pip、`npm install` 与 `npm run build`（`进行中 N 秒` 心跳，完整日志落 `.npm-install.log` / `.build.log`）、以及沙箱镜像构建里的 Ghidra / Jadx（每 3 秒刷新已下载 MB，中断自动续传重试 5 轮）。**判断是否真卡住：看这一行的数字是否还在增长**，长时间不动才是网络或源站问题（处置见 [11 常见问题](#十一常见问题)）。

> [!TIP]
> **镜像源自动选优**：脚本内置多组候选（PyPI：阿里云 / 清华 / 中科大；npm：淘宝 npmmirror / 华为云 / 腾讯云；Node.js 二进制：官方 / 清华 / 阿里；apt：阿里云 / 清华 / 中科大 **外加当前在用的那个源**），启动时**并发测速**（各取前 256 KB，约 8 秒）后自动使用最快的那个 —— 不必再手工换源。
> apt 源只在当前不是最快时才切换（逐文件备份为 `*.ravenholt.bak`，日志里给出回滚方式，且只改源行、不碰注释）；当前源本来就最快时**完全不动机器**。传统 `/etc/apt/sources.list` 与 deb822 格式的 `sources.list.d/*.sources` 都支持。
> 想固定某个源，用环境变量覆盖即可：`PIP_INDEX_URL=` / `NPM_REGISTRY=` / `NODE_MIRROR=`；想跳过测速加 `--no-mirror-probe`。

> [!IMPORTANT]
> 管理员口令由脚本随机生成，**只在终端打印一次**，请立即保存。
> 若忘记，删除 `.ravenholt/config.json` 后重跑 `bash setup.sh` 可重新生成（会重建数据库口令，需同步更新数据库角色）。

> [!NOTE]
> `--with-sandbox` 构建的一体化镜像（约 5 GB，需联网下载 Ghidra / Jadx / observer_ward 等）。**跳过它也不影响渗透**：会话会自动拉取上游镜像（约 4 GB）执行任务，只是缺少定制工具集与平台容器控制台。

### 5.3 手动分步部署

适合需要逐项控制的环境。

**第 1 步：系统依赖**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-client \
                    curl openssl ca-certificates git
# Node.js（构建前端需要；以下二选一，方式 A 与 setup.sh 的做法一致）
# 方式 A：官方二进制解压到 /usr/local（避开发行版仓库的老版本）
curl -fsSL https://nodejs.org/dist/v22.11.0/node-v22.11.0-linux-x64.tar.xz \
  | sudo tar -xJ -C /usr/local --strip-components=1
# 方式 B：用 nodesource 的源
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs
# Docker（完整功能必需）
sudo apt install -y docker.io && sudo systemctl enable --now docker
```

校验：`python3 -V`（≥3.12）、`node -v`（≥20.19）、`psql --version`、`docker info`。

**第 2 步：数据库**

```bash
sudo systemctl start postgresql
sudo -u postgres psql -c "CREATE USER root WITH PASSWORD '你的数据库口令';"
sudo -u postgres psql -c "CREATE DATABASE ravenholt OWNER root;"
```

> 口令须与第 3 步 `config.json` 的 `database.password` 保持一致。

**第 3 步：配置文件（关键，别漏）**

```bash
cp .ravenholt/config.json.example .ravenholt/config.json
cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
```

- `.ravenholt/config.json`：编辑 `system.encrypt_key`（≥32 位随机串，必改）、`system.bootstrap_admin`（管理员邮箱与强口令）、`database`、`agents.*`（LLM 的 `api_key` / `base_url` / `model`）。
- `.ravenholt/policy.yaml`：**红线策略，平台对它是 fail-closed** —— 文件缺失 / YAML 语法错误 / 校验失败，平台会**拒绝启动**。`rate_limit`、`sandbox`、`kill_switch`、`audit` 四节的 `enabled` 必须为 `true`。
- `.ravenholt/skill_routes.yaml`（**可选**）：技能路由表的实例覆盖层。缺失时使用工厂默认（`core/strix_runtime/skill_routes.default.yaml`）。

**第 4 步：Python 依赖**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**第 5 步：构建前端（源码部署必需）**

```bash
cd web && npm install --include=optional && npm run build && cd ..
# 若仍报 MODULE_NOT_FOUND（缺 rolldown 平台原生绑定）：
#   从报错里读出绑定名（如 linux-x64-gnu），再按 rolldown 的版本显式安装：
#   rd_ver=$(node -p "require('rolldown/package.json').version")
#   npm install --no-save "@rolldown/binding-linux-x64-gnu@$rd_ver"
#   npm run build
```

> **源码部署下本步必做**：`web/dist-app` 是构建产物、不入库；不构建则 API 能通但控制台页面加载不出来（空白 / 404）。用 Docker / Compose 部署时由镜像构建阶段生成，**不需要宿主装 Node**。

**第 6 步：构建一体化沙箱镜像（完整功能必需）**

```bash
cd sandbox && bash build.sh      # 产出 sandbox-runtime:latest（仅 x64）
cd ..
```

构建完成后，**让会话与平台容器都使用它** —— 在 `.ravenholt/config.json` 里填：

```json
"sandbox": {
    "network": "ravenholt-lan",
    "image": "sandbox-runtime:latest"
}
```

再到控制台**「沙箱镜像」**页新增一条记录（`image_name` 填 `sandbox-runtime:latest`，`Control Port` 填 `8000`），之后才能在「沙箱容器」页创建带终端/文件/noVNC 的容器。

> `sandbox.image` 留空时，会话使用上游 `ghcr.io/usestrix/strix-sandbox:1.3.0`（首次会话自动拉取）。

**第 7 步：启动**

```bash
bash serve.sh start              # 后台常驻（推荐）
# 或前台调试：
bash serve.sh run
```

访问 <http://127.0.0.1:8000>。

### 5.4 Docker Compose 部署

适合把控制面与数据库一起容器化。

```bash
# 前置：1) 已准备 .ravenholt/config.json 与 .ravenholt/policy.yaml
#          （policy.yaml 缺失或非法时平台 fail-closed 拒绝启动，容器会启动失败）
#       2) 已在宿主构建一体化镜像 sandbox-runtime:latest（app 容器内不含 sandbox/ 目录）
docker compose -f docker-compose.prod.yml up -d --build
```

> 应用镜像由根目录 `Dockerfile` **多阶段构建**：Node 阶段现场执行 `npm ci && npm run build` 生成前端产物并拷入运行镜像，因此**不要求仓库里已有 `web/dist-app`**，也不要求宿主安装 Node；镜像内已含 vendor 的 `strix/` 运行时；`./.ravenholt` 由 Compose 挂载进容器作为运行时配置；`app` 通过挂载宿主 Docker socket 使用沙箱镜像。

> [!TIP]
> **国内网络下构建慢或失败时**：`Dockerfile` 提供两个**可选**镜像源参数，默认走官方源（不传即保持原行为）——
> `--build-arg PIP_INDEX_URL=<PyPI 镜像>`（例如 `https://mirrors.aliyun.com/pypi/simple/`）
> 与 `--build-arg NPM_REGISTRY=<npm 镜像>`（例如 `https://registry.npmmirror.com`）。
> 手工构建示例：
>
> ```bash
> docker build --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
>              --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
>              -t ravenholt:latest .
> ```
>
> `docker compose ... up -d --build` 不便直接传参，可先手工构建应用镜像再 `up`，或在 compose 文件的 `build.args` 下配置同名参数。

> [!CAUTION]
> **Compose 的配置来源（重要，别用错来源）**：编排内置的 `postgres` 服务口令固定为 `123456`（见 `docker-compose.prod.yml`），与仓库自带的 `.ravenholt/config.json.example` 一致。因此 Compose 部署请**直接复制示例**：
>
> ```bash
> cp .ravenholt/config.json.example .ravenholt/config.json
> cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
> ```
>
> **不要复用 `bash setup.sh`（5.2）生成的 `config.json`**：该脚本会为数据库生成**随机口令**，与 Compose 的 `postgres` 固定口令不一致，app 将连不上数据库、启动失败。

该编排包含三个服务：

| 服务 | 说明 |
| --- | --- |
| `app` | 构建镜像 `ravenholt:latest`；`network_mode: host`；挂载 `./.ravenholt` 与 `/var/run/docker.sock`（用于创建沙箱容器） |
| `postgres` | `postgres:16-alpine`，数据落在 `./.postgres-data` |
| `pgadmin` | <http://127.0.0.1:5433>，用于图形化连接数据库 |

> 注意：`app` 使用 host 网络并挂载 Docker socket（需要创建沙箱容器），请仅在受控主机上使用。
> 开发环境也可用 `docker compose -f docker-compose.dev.yml up -d` 只起数据库。

### 5.5 安装后验证

按顺序逐条检查，全部通过即代表「完整功能已就绪」：

```bash
# 1) 服务在跑、健康检查通过
bash serve.sh status

# 2) 数据库连通
psql -h 127.0.0.1 -U root -d ravenholt -c '\dt' | head

# 3) 沙箱镜像就位（完整功能需要 sandbox-runtime，能跑会话还需要 strix-sandbox）
docker images | grep -E 'strix-sandbox|sandbox-runtime'

# 4) 会话沙箱确实在用一体化镜像（值应为 sandbox-runtime:latest）
grep -A3 '"sandbox"' .ravenholt/config.json

# 5) 联网检索后端可达
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8888/

# 6) 镜像与代码版本对齐（vendor 升级后尤其要看）
.venv/bin/python scripts/verify_strix_version_alignment.py
```

浏览器打开 <http://127.0.0.1:8000>，用管理员邮箱与口令登录，即完成安装。

---

## 六、配置说明

### 6.1 `.ravenholt/config.json`

| 段 | 关键项 | 说明 |
| --- | --- | --- |
| `system` | `listen_addr` / `listen_port` | 控制面监听地址与端口（示例为 `0.0.0.0:8000`） |
| | `encrypt_key` | 数据加密密钥，**必须改**为 ≥32 位随机串 |
| | `bootstrap_admin` | 首次启动自动创建的管理员（`enabled` / `username` / `email` / `password`）；登录用邮箱 |
| `database` | `host` / `port` / `database` / `username` / `password` | PostgreSQL 连接；本机部署填 `127.0.0.1` |
| | `pool_size` / `max_overflow` / `pool_timeout_seconds` / `pool_recycle_seconds` / `pool_pre_ping` | 连接池参数 |
| `agents` | `cso` … | 各 agent 的 LLM 配置：`api_key` / `base_url` / `model` / `use_responses` / `context_window`；agent 列表由本段决定 |
| `agent_pool` | `max_size` / `ttl_seconds` / `sweep_interval_seconds` | 进程内智能体会话池 |
| `agent_runtime` | `main_max_turns` / `subordinate_max_turns` / `model_stream_idle_timeout_seconds` / `context_compression_*` | 回合上限与上下文压缩 |
| `sandbox` | `network` | 沙箱容器接入的自定义 docker 网络名（如 `ravenholt-lan`）。为空则用默认 bridge + 端口发布；非空时由 `sandbox/setup_macvlan.sh` 自动派生并注入 `STRIX_DOCKER_SANDBOX_NETWORK` |
| | `image` | **会话沙箱使用的镜像**。留空 = 上游 `ghcr.io/usestrix/strix-sandbox:1.3.0`；填 `sandbox-runtime:latest` = 使用一体化镜像（含定制工具集） |
| `archive` | `enabled` / `capture_*` / `retention_days` / `queue_max` 等 | 事件总线旁路归档 |
| `integrations` | `web_search_provider` | 联网检索后端：`auto` / `exa` / `perplexity` / `searxng` |
| | `exa_api_key` / `perplexity_api_key` | 第三方检索 Key（可留空） |
| | `searxng_base_url` | 自建 SearXNG 地址，默认 `http://127.0.0.1:8888` |
| | `searxng_auto_provision` | 不可达时是否自动拉起 SearXNG 容器，默认开 |
| | `searxng_bind_addr` | SearXNG 容器端口发布的宿主地址，默认 `0.0.0.0` |

> **SearXNG 与公网部署**：平台启动时会 best-effort 拉起本机 SearXNG 容器（`searxng_auto_provision`，默认开），并默认把端口发布在 `0.0.0.0`（`searxng_bind_addr`）——这样 macvlan 沙箱（经宿主 LAN IP）与回退 bridge 沙箱（经 docker 网关 `172.17.0.1`）都能检索它。该服务**无鉴权**（`limiter: false`、`public_instance: false`），若平台跑在公网可直达的机器上，请把 `searxng_bind_addr` 改为 `127.0.0.1`（放弃沙箱内直连）或宿主内网 IP，或用宿主防火墙只放行沙箱来源，避免被滥用为开放检索代理。

> 改完配置后需重启生效：`bash serve.sh restart`。

### 6.2 `.ravenholt/policy.yaml`（红线策略，fail-closed）

- **文件缺失 / YAML 非法 / 校验失败 → 平台拒绝启动**，这是有意设计。
- `rate_limit`、`sandbox`、`kill_switch`、`audit` 四节属 Tier-1 安全网，`enabled` 必须为 `true`（参数可自由调）。
- `approvals` 定义「默认不做、须你同意」的风险动作（改密码、破坏性操作、执行型载荷、修改目标数据、登出/吊销、CORS 探测、越权写）；`redline.dos_signals` 是**绝对红线**——DoS 类命中即硬拒，控制台不提供放行开关。
- `approval_wait_seconds` 控制审批卡片等待时长，超时按**拒绝**处理（fail-closed）。
- `report_gate` 是报告结构门：finding 离开 draft 前必须满足最小要素（绑资产、标题/描述长度、影响说明）。
- 控制台改动**即时生效并写回本文件**（整体重写、注释折叠）；手工改动需重启生效。

### 6.3 环境变量

平台会把配置注入下列 strix 读取的环境变量（一般无需手工设置）：

| 变量 | 来源 | 作用 |
| --- | --- | --- |
| `STRIX_LLM` / `LLM_API_KEY` 等 | `agents` 段 | 注入给 LiteLLM 的模型与密钥 |
| `STRIX_WEB_SEARCH_PROVIDER` / `EXA_API_KEY` / `PERPLEXITY_API_KEY` / `STRIX_SEARXNG_BASE_URL` | `integrations` 段 | 联网检索后端与密钥 |
| `STRIX_DOCKER_SANDBOX_NETWORK` | `sandbox.network` | 沙箱容器接入的 docker 网络 |
| `STRIX_IMAGE` | `sandbox.image` | **会话沙箱使用的镜像**；留空即不注入，strix 回退其默认上游镜像 |

可手工导出的开关：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `RAVENHOLT_SEARXNG_AUTOPROVISION=0` | 开 | 关闭 SearXNG 容器自动保障（优先级高于配置项） |
| `SANDBOX_CONTAINER_NAME_PREFIX` | `ravenholt-sandbox` | 平台沙箱容器名前缀；设为空串则回退为按镜像短名生成 |
| `SANDBOX_COMMAND_WORKDIR` | `/workspace` | 沙箱内执行命令的工作目录（两种镜像的 WORKDIR 不同时用它切换） |

> 手工 `export STRIX_IMAGE=...` 会被 `sandbox.image` 覆盖（配置优先），因此推荐直接改配置文件。

### 6.4 管理 LLM API Key

```bash
bash config-tool.sh list                                  # 查看各 agent 配置摘要
bash config-tool.sh set sk-xxxx --url https://api.deepseek.com/v1 --model deepseek-v4-flash
bash config-tool.sh clear                                 # 清空所有 Key
```

也可以在控制台**系统配置**页填写；两处等价。

### 6.5 联网检索配置

| provider | 需要什么 | 说明 |
| --- | --- | --- |
| `searxng`（默认零配置） | 无 Key | 平台自动拉起本机 SearXNG 容器（带镜像源回退） |
| `exa` | `exa_api_key` | 需自行申请 |
| `perplexity` | `perplexity_api_key` | 需自行申请 |
| `auto` | 无 | 依次尝试 `exa → perplexity → searxng`，谁可用用谁 |

沙箱内如需直接访问本机 SearXNG，地址要用**宿主 LAN IP**（如 `http://192.168.5.139:8888`）而不是 `127.0.0.1`：沙箱容器有独立 IP，`127.0.0.1` 指向容器自身；且容器内出站统一经 Caido 代理转发，目标不可达时会返回一个 ~9 KB 的 `<title>Caido</title>` 错误页（那是代理的报错，不是目标响应）。

### 6.6 沙箱镜像：构建与启用

```bash
cd sandbox && bash build.sh        # 产出 sandbox-runtime:latest
# 换基础镜像（例如国内镜像源）：
# docker build --build-arg STRIX_SANDBOX_IMAGE=<镜像地址> -t sandbox-runtime:latest .
# 换 GitHub 加速前缀（不指定时**自动测速挑最快通道**：直连 / gh-proxy / ghfast）：
# GITHUB_MIRROR=https://ghfast.top/ bash build.sh   # 显式指定
# GITHUB_MIRROR= bash build.sh                      # 强制直连
```

**一体化镜像的来源优先级**（`setup.sh` 会自动按这个顺序判断）：

1. 本地已有 `sandbox-runtime:latest` → 直接用，不动网络；
2. 否则**先尝试拉取 CI 已构建好的 `ghcr.io/xiaoliuhua2/ravenholt-sandbox:latest`**（通常几分钟，无需本地 5 GB 构建）—— 拉成功即 `docker tag` 成 `sandbox-runtime:latest` 并写入 `config.json`；
3. 拉不到（未发布 / 未设为 Public / 未 `docker login ghcr.io` / 无网络）时，才按 `--with-sandbox` 决定本地构建（要下约 1.5 GB GitHub 资源），否则给出上面两种取得方式的提示。

> 换你自己的 GHCR 仓库 / 改 tag：`SANDBOX_REMOTE_IMAGE=ghcr.io/<owner>/<image>:<tag> bash setup.sh`；离线环境想强制走本地构建：`SANDBOX_REMOTE_IMAGE= bash setup.sh --with-sandbox`。

> [!TIP]
> **带宽不足时的做法**：构建要下载约 1.5 GB 的 Ghidra 及若干工具包。若本机链路很慢（实测有环境经加速前缀只有几十 KB/s，1.5 GB 需数小时且会被代理掐断），更实际的是**在带宽好的机器上构建，再迁移镜像**：
>
> ```bash
> # 有网机器上
> docker save sandbox-runtime:latest | gzip > sandbox-runtime.tgz
> # 目标机器上
> gunzip -c sandbox-runtime.tgz | docker load
> ```
>
> 完全不构建也不影响渗透：会话会退回上游镜像 `ghcr.io/usestrix/strix-sandbox:1.3.0`（含 Caido + Kali 工具链），只是缺少逆向工具与容器控制台。

启用分两处（缺一不可，用途不同）：

| 用途 | 位置 | 填什么 |
| --- | --- | --- |
| agent **会话**沙箱 | `.ravenholt/config.json` → `sandbox.image` | `sandbox-runtime:latest` |
| 平台**沙箱容器**控制台 | 控制台「沙箱镜像」页新增记录 | `image_name` = `sandbox-runtime:latest`，`Control Port` = `8000` |

改完 `sandbox.image` 后重启生效（`bash serve.sh restart`）；新的会话才会用新镜像（已运行的会话不受影响）。

---

## 七、启动与运维

```bash
bash serve.sh start      # 后台常驻（默认动作；带 PID 文件、端口健康检查、日志落盘）
bash serve.sh run        # 前台运行（调试用；启动时在屏幕打印管理员账号与口令，Ctrl+C 停止）
bash serve.sh status     # 查看进程 / 端口 / 健康检查
bash serve.sh logs 40    # 查看启动日志（-f 持续跟踪）
bash serve.sh restart    # 重启
bash serve.sh stop       # 停止（SIGTERM 优雅退出）
```

> [!TIP]
> 启动时（`serve.sh start` / `run`）会从 `.ravenholt/config.json` 读出并打印管理员邮箱与口令，方便首次登录；若 `bootstrap_admin` 未启用则提示相应信息。

- 应用日志：`.ravenholt/app.log`
- 服务日志：`logs/serve.log`
- 访问地址：<http://127.0.0.1:8000>；API 文档：<http://127.0.0.1:8000/docs>
- `serve.sh start` 还会：按已安装主版本号动态启动 PostgreSQL、必要时自动创建 venv 并装依赖、执行 `sandbox/setup_macvlan.sh` 准备沙箱网络。

**一键升级**

```bash
bash update.sh                      # git pull → 更新依赖 → 必要时重建前端 → 重启服务
bash update.sh --no-pull            # 不拉代码，只按当前代码重建依赖并重启
bash update.sh --rebuild-frontend   # 强制重建前端产物
bash update.sh --with-sandbox       # 额外重建一体化沙箱镜像（下载量大、耗时长）
```

`update.sh` 复用 `setup.sh --no-deps` 的幂等逻辑：pip 依赖已满足则跳过、`web/dist-app` 已存在则跳过构建、`config.json` / `policy.yaml` 一律不覆盖 —— 因此可以放心反复执行；最后调用 `serve.sh restart` 让新代码生效。有本地改动时 `git pull --ff-only` 会失败，脚本只提示、不覆盖你的改动。

---

## 八、快速上手

### 8.1 首次登录

1. 打开 <http://127.0.0.1:8000>，用管理员邮箱与口令登录。

   <img src="docs/public/images/login.png" alt="登录页" width="820" />

2. 进入**系统配置**填好 `agents` 的 LLM API Key（或提前用 `config-tool.sh set` 设置）—— **这是 agent 能干活的前提**。

### 8.2 启用完整功能

按顺序执行，即可逐项把能力全部打开：

| 步骤 | 操作 | 得到什么 |
| --- | --- | --- |
| 1 | `bash setup.sh --with-sandbox`（或在手动部署里走完 5.3 的第 1–6 步） | 平台、数据库、前端、一体化沙箱镜像全部就位 |
| 2 | 确认 `.ravenholt/config.json` 的 `sandbox.image` = `sandbox-runtime:latest` | 会话使用定制镜像（Ghidra/Jadx/observer_ward/agent-browser） |
| 3 | 控制台「沙箱镜像」页新增记录（`Control Port` = `8000`） | 「沙箱容器」页可创建带终端/文件/noVNC 的容器 |
| 4 | 填 LLM API Key（系统配置页） | 会话对话与 agent 执行可用 |
| 5 | 新建**工作项目**，填写范围与目标 | 资产、发现、证据、攻击路径有归属 |
| 6 | 首次发起会话 | 自动创建沙箱容器（含 Caido），可按需拉取镜像 |
| 7 | 确认 `curl http://127.0.0.1:8888/` 返回 200 | 联网检索可用（无需任何 Key） |
| 8 | （可选）「出口代理」页配置代理链路 | 沙箱出网可控可审计 |
| 9 | （可选）检查 `policy.yaml` 的 `approvals` / `redline` | 审批门槛与绝对红线符合预期 |

### 8.3 一次典型渗透流程

1. 新建工作项目 → 填范围（授权的域名/IP 列表）。
2. 操作台新建会话 → 选择 agent 预设 → 描述任务目标。
3. agent 自动创建沙箱容器并在其中执行侦察（nmap / httpx / katana 等），流量经 Caido 落库。
4. 在容器面板查看终端输出、用**请求库**复核 Caido 抓到的报文（`list_requests` / `view_request` / `repeat_request`）。
5. 命中高风险动作时，**策略审批**会挂起等你在会话内点「同意」。
6. 发现写入项目（含证据与影响），结束后导出报告并核对**可回放时间线**与**审计日志**。

---

## 九、界面一览

| 操作台 | 工作项目 |
| --- | --- |
| <img src="docs/public/images/playground.png" alt="操作台" width="420" /> | <img src="docs/public/images/work-projects.png" alt="工作项目" width="420" /> |

| 系统配置 | 系统用户 |
| --- | --- |
| <img src="docs/public/images/system-config.png" alt="系统配置" width="420" /> | <img src="docs/public/images/system-users.png" alt="系统用户" width="420" /> |

| 策略审批 | 审计日志 |
| --- | --- |
| <img src="docs/public/images/policy-confirmations.png" alt="策略审批" width="420" /> | <img src="docs/public/images/audit-events.png" alt="审计日志" width="420" /> |

| 出口代理 | 落地页 |
| --- | --- |
| <img src="docs/public/images/egress-proxies.png" alt="出口代理" width="420" /> | <img src="docs/public/images/landing.png" alt="落地页" width="420" /> |

---

## 十、目录结构

```
ravenholt/
├── app.py / main.py / config.py / database.py    # 应用装配、入口、配置、数据库
├── core/            # 运行时核心：agent、会话池、策略引擎、strix 运行时、事件归档
├── service/ handler/ router/ schema/ model/       # 分层：逻辑 / 处理 / 路由 / 契约 / 模型
├── middleware/ utils/                             # 鉴权、统一响应等中间件与工具
├── strix/           # vendor 的 strix 运行时与技能库（由 .strix-vendor.json 校验上游 commit 与逐文件哈希）
├── .strix-vendor.json  # vendor 清单：上游仓库 / commit / 文件哈希 / 受保护前缀
├── sandbox/         # 一体化沙箱镜像构建
│   ├── Dockerfile           # 基于上游镜像叠加定制能力
│   ├── entrypoint.sh        # 先挂附加服务，再交给上游 entrypoint 启动 Caido
│   ├── supervisord.conf     # Xvfb / x11vnc / noVNC / tor / Go 控制面
│   ├── proxy/               # 容器内 Go 控制面（终端/文件/egress）
│   ├── .agents/skills/      # 容器内技能资源（随镜像分发）
│   └── setup_macvlan.sh     # 沙箱网络（按宿主自动派生）
├── web/             # 前端源码（src / openapi.json）；dist-app 为构建产物，不入库
├── docs/            # VitePress 文档站（en / zh）
├── scripts/         # 工具与自检脚本（sync_strix.py 同步上游、export_schema、verify_*_selftest、verify_strix_version_alignment 等）
├── tests/           # 单元测试
├── .ravenholt/      # 运行时配置：config.json / policy.yaml / skill_routes.yaml（均不入库）
├── .github/         # CI：build-frontend（构建 dist-app 并作为 Release 附件）、build-sandbox-image（构建并推 GHCR）
├── setup.sh         # 一键部署脚本
├── update.sh        # 一键升级（git pull → 更新依赖 → 重启服务）
├── serve.sh         # 服务管理（start/stop/restart/status/logs/run；启动打印账号口令）
├── config-tool.sh   # LLM API Key 管理
├── docker-compose.prod.yml / .dev.yml
└── requirements.txt
```

---

## 十一、常见问题

**Q：启动即退出，日志显示策略相关报错？**
A：`.ravenholt/policy.yaml` 缺失或非法。平台对红线策略是 **fail-closed**，必须存在且合法：
`cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml`。

**Q：Docker 未安装可以运行吗？**
A：可以启动平台并使用控制面（登录、项目、策略、审计、报告都正常），但**渗透/代码审计的沙箱执行面不可用** —— 发起会话时才会报错。

**Q：不构建 `sandbox-runtime:latest` 能不能做渗透？**
A：能。会话沙箱默认使用上游镜像 `ghcr.io/usestrix/strix-sandbox:1.3.0`（含 Caido 与 Kali 工具链），首次会话自动拉取。构建一体化镜像的收益是：额外获得 Ghidra / Jadx / apktool / binwalk / observer_ward / agent-browser、容器内技能资源，以及「沙箱容器」页的终端 / 文件 / noVNC。

**Q：构建了镜像，怎么让 agent 会话用它？**
A：`bash setup.sh --with-sandbox` 会自动把镜像名写进 `.ravenholt/config.json` 的 `sandbox.image`。手动部署请自行填 `"image": "sandbox-runtime:latest"` 并 `bash serve.sh restart`。**只构建不配置，会话仍用上游镜像。** 另需在「沙箱镜像」页登记一条记录（`Control Port` = `8000`）才能使用「沙箱容器」页。

**Q：为什么要两个地方登记镜像？**
A：用途不同 —— `config.json` 的 `sandbox.image` 决定 **agent 会话**用哪个镜像；「沙箱镜像」页的记录决定**平台手工创建的容器**用哪个镜像（需要 `Control Port` 才能连上容器内控制面）。

**Q：「沙箱容器」页创建容器后，看不到终端 / 文件 / noVNC 按钮？**
A：该容器用的镜像不含容器内 Go 控制面（例如上游镜像）。用 `sandbox-runtime:latest` 创建的容器才会有这些按钮。

**Q：改网段 / 换到别的局域网后沙箱还能用吗？**
A：能。`sandbox/setup_macvlan.sh` 不写死任何网段 —— 子网、网关、父接口、容器地址段与宿主 shim 地址全部从宿主默认路由动态派生，换网段后重启（`bash serve.sh restart`）会自动重建。

**Q：无法创建沙箱容器？**
A：确认 Docker 守护进程在运行，且平台进程能访问 Docker Socket（Compose 已挂载 `/var/run/docker.sock`）。

**Q：一体化镜像构建失败？**
A：分两种情况。**(1) 卡在拉取阶段**（报 `failed to resolve source metadata for docker.io/docker/dockerfile:1`、`connection refused`、`registry-1.docker.io` 超时）—— 说明本机到 Docker Hub / GHCR 不通；本镜像需要 `debian:trixie-slim`、`golang:trixie`（Docker Hub）与 `ghcr.io/usestrix/strix-sandbox`、`ghcr.io/astral-sh/uv`（GHCR）。处置：给 Docker 配镜像加速（`/etc/docker/daemon.json` 的 `registry-mirrors`，如 `https://docker.m.daocloud.io`）后 `systemctl restart docker`；先手工 `docker pull ghcr.io/usestrix/strix-sandbox:1.3.0` 验证通路；完全离线时在能联网的机器上构建后 `docker save` / `docker load` 迁移。（本仓库的 `sandbox/Dockerfile` 已刻意不写 `# syntax=docker/dockerfile:1`，避免为此多拉一个前端镜像。）**(2) 构建中途失败** —— 确认 x64 架构与足够磁盘（要下载约 1.5 GB 的 Ghidra 等），受限网络可用 `--build-arg STRIX_SANDBOX_IMAGE=<可用镜像源>` 换基础镜像。`sandbox/build.sh` 在失败时会把上述处置打印出来。

**Q：不想本地装 Node / 不想本地构建 5 GB 沙箱镜像？**
A：两条「免构建」路径（CI 已提供）：
① **前端**：打 tag 时 [`.github/workflows/build-frontend.yml`](.github/workflows/build-frontend.yml) 会构建 `web/dist-app` 并作为 Release 附件 `web-dist-app.tar.gz` 发布；下载后 `tar -xzf web-dist-app.tar.gz -C web/` 即可，源码部署不再需要 Node。
② **沙箱镜像**：Actions → `build-sandbox-image` → Run workflow，CI 会构建一体化镜像并推送到 GHCR；本机只需要

```bash
docker pull ghcr.io/<你的用户名>/ravenholt-sandbox:latest
docker tag  ghcr.io/<你的用户名>/ravenholt-sandbox:latest sandbox-runtime:latest
```

这样免去本地拉基础镜像与下载 1.5 GB Ghidra。注意：首次推送后要到 仓库 → **Packages** → `ravenholt-sandbox` → Package settings 把可见性改为 **Public**，否则他人 `docker pull` 需登录 GHCR。

> `setup.sh` 第 7/8 段现在**会自动检测并拉取**这个镜像（拉成功就 `docker tag` 成 `sandbox-runtime:latest` 并写入 `config.json`），不需要手工执行上面的命令 —— 前提是它已发布且可访问；拉不到才回退本地构建（见 [6.6](#66-沙箱镜像构建与启用)）。

**Q：`apt install` 报「无法定位软件包」（例如 `docker.io`）？**
A：绝大多数是**换了 apt 源之后没有刷新包索引** —— 换源只改配置，索引仍是旧源（新机器上甚至为空）留下的，apt 自然"找不到"任何包。`setup.sh` 现在会在换源后**无条件执行 `apt-get update`**，且索引刷新失败时自动回滚到原源；手工操作时请记住：换源后必须先 `apt update`。
若刷新后仍然找不到 `docker.io`，说明该镜像源缺这个包：换回官方源（`http.kali.org` / `kali.download`）再装，或直接用 Docker 官方脚本 `curl -fsSL https://get.docker.com | sh`（脚本本身会告诉你这个方案）。

**Q：`docker pull` 一体化镜像很慢（几小时）？**
A：瓶颈通常不是你的总带宽，而是 **docker 默认只开 3 个并发下载、每层一条单 TCP 连接**，跨境链路上单流常被限到 20~40 KB/s。实测同一个 2.16 GB / 47 层的镜像，在同一台机器上：

| 并发路数 | 合计吞吐 |
| --- | --- |
| 1 路 | 23 KB/s |
| 4 路 | 90 KB/s |
| 10 路 | **183 KB/s**（已接近该链路 200 KB/s 上限） |

所以把并发提到 10 能快约 8 倍：

```bash
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{ "max-concurrent-downloads": 10 }
EOF
sudo systemctl restart docker
docker pull ghcr.io/xiaoliuhua2/ravenholt-sandbox:latest   # 已下完的层会复用，不会重下
```

关于换国内 GHCR 加速站 —— 实测多数不可用，收益有限：

| 站点 | 实测 |
| --- | --- |
| `ghcr.nju.edu.cn` | 能取 manifest，但**层 blob 下载 0 KB/s（不通）** |
| `ghcr.m.daocloud.io` | 层下载 **HTTP 403** |
| `ghcr.dockerproxy.com` | 不通（超时） |
| `ghcr.chenby.cn` | **53 KB/s**，可用，比直连（25~36 KB/s）快约 1.5 倍，可作备选 |

即 `docker pull ghcr.chenby.cn/xiaoliuhua2/ravenholt-sandbox:latest`。注意这是第三方个人维护的加速站，镜像内容是公开的，但可用性不受本项目控制。

**Q：沙箱里 `curl` 目标返回 502，页面标题是 `Caido`？**
A：那是**代理错误页，不是目标响应** —— 沙箱内所有出站 HTTP 都经容器内 Caido 代理，目标不可达时由代理代为报错。用 `curl -s <url> | grep -A8 'c-title"'` 看真实原因（`Failed to query DNS` / `Connection refused` / TLS 握手失败 / timeout），修正 URL 后重试。

**Q：改了配置不生效？**
A：`config.json` 改动需重启（`bash serve.sh restart`），且 `sandbox.image` 只影响**之后新建的会话**；`policy.yaml` 通过控制台改是即时的，手工改需重启。`approvals.allow` 的改动只对新建会话 / 新建子代理生效（提示词在创建 agent 时渲染）。

**Q：`git clone` 后启动，浏览器打开是空白页或 404？**
A：前端产物 `web/dist-app` **不入库**，源码部署必须先构建一次：`cd web && npm install && npm run build`（Node ≥ 20.19）。用 Docker / Compose 部署时由镜像构建阶段自动生成，无需本步。

**Q：`npm run build` 失败？**
A：多数是 Node 版本（需 ≥ 20.19），或**可选原生绑定缺失** —— Vite 8 的 rolldown 需要平台绑定（如 `@rolldown/binding-linux-x64-gnu`），报错为 `Cannot find module '../rolldown-binding.<平台>.node'`。**实测：`npm install --include=optional` 往往补不回**（`package-lock.json` 里该条目已存在，npm 认为无需处理）；有效做法是**按 rolldown 的实际版本显式安装该绑定包**：

```bash
cd web
rd_ver=$(node -p "require('rolldown/package.json').version")
npm install --no-save --prefer-offline "@rolldown/binding-linux-x64-gnu@$rd_ver"
npm run build
```

`setup.sh` 第 6/8 段已自动做这两步（先补装、失败再从构建日志解析绑定名并按版本显式安装）。两条都失败时，换 npm 源重试：`npm config set registry https://registry.npmmirror.com`，或删掉 `web/node_modules` 重装。

**Q：页面还是旧内容？**
A：landing 等页面是**构建期固化**的 —— 改源码后必须重新 `cd web && npm run build`，再硬刷新浏览器（Ctrl+F5）。

**Q：Compose 部署后 app 连不上数据库？**
A：多半是复用了 `setup.sh` 生成的 `config.json`（随机库口令）与 Compose 固定口令 `123456` 不一致。见 [5.4](#54-docker-compose-部署) 的配置来源说明。

**Q：部署在公网要注意什么？**
A：三件事 —— ① 收窄 `searxng_bind_addr`（该服务无鉴权）；② 控制面监听在 `0.0.0.0:8000`，建议用反向代理加 TLS 与访问控制；③ 沙箱容器需挂载 Docker socket，host 网络下只应部署在受控主机。

---

## 十二、许可

本项目基于 **MIT License** 发布，版权归 2026 `yv1ing` 与 `xiaoliuhua2`。详见 [LICENSE](./LICENSE)。

内部 vendor 的 strix 运行时按其原始许可（Apache-2.0）保留版权声明；一体化沙箱镜像在运行时**二次分发**了第三方二进制（Ghidra / Jadx / observer_ward / agent-browser-cli / Kali 工具链等），部署与再分发时请遵守各自的许可条款。使用本平台进行任何测试前，请确保已获得目标系统的明确授权。
