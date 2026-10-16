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
4. [环境要求](#四环境要求)
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

## 二、功能特性

- **操作台（Playground）**：多智能体会话、流式对话、子智能体面板、思考过程内联展示、可回放时间线；会话列可拖拽调宽、可一键收起。
- **沙箱执行面**：基于 Docker 的定制沙箱容器，提供终端、文件管理、noVNC 远程画面与 Caido 抓包/重放；容器按会话自动 provision。
- **工作项目（WorkProject）**：项目元数据、负责人、范围资产、会话、记录、关系图与攻击路径；发现携带证据与影响。
- **源码审计通道（白盒）**：上传源码包后可走白盒分轨，技能路由与提示词随之切换。
- **出口代理**：受控网络出口的配置与管理（代理出口链路）。
- **策略审批**：红线策略判定动作是否放行；高风险动作进入审批队列，由管理员批准/拒绝。
- **审计日志**：关键动作与事件的审计追踪（动作、判定、拦截原因等）。
- **系统用户 / 系统配置**：账号与角色权限、运行参数与集成配置。
- **可回放时间线**：所有来源按时间归并为唯一顺序视图，支持事后逐条复核。

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
│  沙箱执行面（Docker）                         │
│  sandbox-runtime 镜像 · Kali 工具链 · Caido   │
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
| 数据库 | PostgreSQL 16 |
| 部署 | venv 直跑 / Docker Compose |

## 四、环境要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | **Linux x64**（推荐 Kali / Debian） | 沙箱镜像仅支持 x64/amd64，不支持 arm64 |
| Python | **≥ 3.12**（推荐 3.13） | 需 `venv` 模块 |
| Node.js | **≥ 20.19**（推荐 22+） | Vite 8 要求；仓库 Dockerfile 使用 node:22 |
| PostgreSQL | **16+** | 数据持久化 |
| Docker | 建议安装 | 渗透/审计沙箱的运行时；缺失则执行面不可用 |
| 磁盘 | 建议 ≥ 2 GB（沙箱镜像另需 3+ GB） | 沙箱镜像含 Ghidra/Jadx 等工具链 |

## 五、下载与安装部署

提供三种方式，任选其一。**一键脚本推荐用于首次部署。**

### 5.1 下载源码

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git
cd ravenholt
```

> 也可以直接下载 ZIP 解压。仓库已 vendor 完整的 `strix/` 运行时与**预构建好的前端产物** `web/dist-app`，开箱即可用。

### 5.2 一键部署（推荐）

```bash
# 1) 先体检：只检测环境，不改动任何文件
bash setup.sh --check

# 2) 正式部署：检测 → 装系统依赖 → 初始化配置 → 建库
#    → 装 Python 依赖 → 构建前端 → 自检
bash setup.sh

# 可选：一并自动构建渗透沙箱镜像（下载量大、耗时长）
bash setup.sh --with-sandbox
```

脚本共 8 段，逐段打印结果：

| 段 | 内容 |
| --- | --- |
| 1/8 环境检测 | 系统/架构/Python/Node/Docker/PostgreSQL/权限/端口/磁盘，逐项给出结论与修复命令 |
| 2/8 系统依赖 | 缺什么装什么（apt），装完复检 Python/venv 等硬性依赖 |
| 3/8 配置初始化 | 生成 `.ravenholt/config.json`（随机 `encrypt_key`、数据库口令、管理员口令）与 **`policy.yaml`** |
| 4/8 PostgreSQL | 启动服务、建角色与数据库，口令与 config.json 对齐 |
| 5/8 Python 依赖 | 建 `.venv` 并 `pip install -r requirements.txt` |
| 6/8 前端构建 | `web/` 下 `npm install` + `npm run build`，产出 `web/dist-app` |
| 7/8 沙箱镜像 | 检测 Docker/架构；提示或按 `--with-sandbox` 自动构建 |
| 8/8 安装后自检 | 语法编译、config/policy 加载、`create_app` 装配冒烟 |

脚本**幂等**：已存在的 `config.json` / `policy.yaml` 不会被覆盖。

> [!IMPORTANT]
> 管理员口令由脚本随机生成，**只在终端打印一次**，请立即保存。
> 若忘记，删除 `.ravenholt/config.json` 后重跑 `bash setup.sh` 可重新生成（会重建数据库口令，需同步更新数据库角色）。

### 5.3 手动分步部署

适合需要逐项控制的环境。

**第 1 步：系统依赖**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-client \
                    curl openssl ca-certificates
# Node.js（Debian/Kali 自带版本可能过旧，推荐 nodesource）
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
# Docker（可选，沙箱执行面需要）
sudo apt install -y docker.io && sudo systemctl enable --now docker
```

校验：`python3 -V`（≥3.12）、`node -v`（≥20.19）、`psql --version`、`docker -v`。

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

- `.ravenholt/config.json`：编辑 `system.encrypt_key`（≥32 位随机串，必改）、`system.bootstrap_admin`（管理员邮箱与强口令）、`database`（本机则 `host=127.0.0.1`）、`agents.*`（LLM 的 `api_key` / `base_url` / `model`）。
- `.ravenholt/policy.yaml`：**红线策略，平台对它是 fail-closed** —— 文件缺失 / YAML 语法错误 / 校验失败，平台会**拒绝启动**。`rate_limit`、`sandbox`、`kill_switch`、`audit` 四节的 `enabled` 必须为 `true`。
- `.ravenholt/skill_routes.yaml`（**可选**）：技能路由表的实例覆盖层。缺失时使用工厂默认（`core/strix_runtime/skill_routes.default.yaml`）。

**第 4 步：Python 依赖**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**第 5 步：前端构建**

```bash
cd web
npm install
npm run build      # 内部依次执行 generate:api -> tsc -> vite build
cd ..
```

产出 `web/dist-app`，后端会自动挂载托管。

> [!NOTE]
> 仓库已内置预构建的 `web/dist-app`，跳过本步也能启动；仅在改动前端源码后才需重新构建。

**第 6 步：沙箱镜像（可选，执行面需要）**

```bash
cd sandbox && bash build.sh      # 产出 sandbox-runtime:latest（仅 x64）
cd ..
```

沙箱容器在首次使用时由平台按会话自动 provision 镜像记录，无需手工登记。

**第 7 步：启动**

```bash
python main.py                   # 前台（Ctrl+C 停止）
# 或后台常驻：
bash serve.sh start
```

访问 <http://127.0.0.1:8000>。

### 5.4 Docker Compose 部署

适合把控制面与数据库一起容器化。

```bash
# 前置：1) 已准备 .ravenholt/config.json 与 .ravenholt/policy.yaml
#          （policy.yaml 缺失或非法时平台 fail-closed 拒绝启动，容器会启动失败）
#       2) 已构建沙箱镜像 sandbox-runtime:latest
docker compose -f docker-compose.prod.yml up -d --build
```

> 应用镜像（`Dockerfile`）已内置 vendor 的 `strix/` 运行时与构建好的前端 `web/dist-app`，无需额外挂载；`./.ravenholt` 由 Compose 挂载进容器作为运行时配置。

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

## 六、配置说明

### `.ravenholt/config.json`

| 段 | 关键项 | 说明 |
| --- | --- | --- |
| `system` | `listen_addr` / `listen_port` | 监听地址与端口（默认 `0.0.0.0:8000`） |
| | `encrypt_key` | 数据加密密钥，**必须改**为 ≥32 位随机串 |
| | `bootstrap_admin` | 首次启动自动创建的管理员（`username` / `email` / `password`）；登录用邮箱 |
| `database` | `host` / `port` / `database` / `username` / `password` | PostgreSQL 连接；Compose 部署时 `host` 填 `127.0.0.1` |
| `agent_runtime` | `main_max_turns` / 上下文压缩相关 | 运行时回合上限与上下文压缩阈值 |
| `agent_pool` | `max_size` / `ttl_seconds` | 智能体会话池 |
| `agents` | `cso` … | 各 agent 的 LLM 配置：`api_key` / `base_url` / `model` / `context_window` |
| `integrations` | `web_search_provider` 等 | 联网检索后端（如 SearXNG / Exa / Perplexity） |

> 智能体列表由本配置的 `agents` 段决定（默认只含 `cso` 一条预设），非固定静态角色表。

### 管理 LLM API Key

```bash
bash config-tool.sh list                                  # 查看各 agent 配置摘要
bash config-tool.sh set sk-xxxx --url https://api.deepseek.com/v1 --model deepseek-v4-flash
bash config-tool.sh clear                                 # 清空所有 Key
```

### 策略与技能路由

- `.ravenholt/policy.yaml`：红线策略（fail-closed）。控制台的改动即时生效并写回本文件。
- `.ravenholt/skill_routes.yaml`：技能路由实例覆盖层（可选）。

## 七、启动与运维

```bash
bash start.sh            # 前台运行（启动时在屏幕打印管理员账号与口令；Ctrl+C 停止）
bash serve.sh start      # 后台常驻（带 PID 文件、端口健康检查、日志落盘）
bash serve.sh status     # 查看进程 / 端口 / 健康检查
bash serve.sh logs 40    # 查看启动日志（-f 持续跟踪）
bash serve.sh restart    # 重启
bash serve.sh stop       # 停止（SIGTERM 优雅退出）
```

> [!TIP]
> `bash start.sh` 会从 `.ravenholt/config.json` 读出并打印管理员邮箱与口令，方便首次登录；若 `bootstrap_admin` 未启用则提示相应信息。

- 应用日志：`.ravenholt/app.log`
- 服务日志：`logs/serve.log`
- 访问地址：<http://127.0.0.1:8000>；API 文档：<http://127.0.0.1:8000/docs>

## 八、快速上手

1. 打开 <http://127.0.0.1:8000>，用管理员邮箱与口令登录。

   <img src="docs/public/images/login.png" alt="登录页" width="820" />

2. 进入**系统配置**填好 `agents` 的 LLM API Key（或提前用 `config-tool.sh set` 设置）。
3. 进入**工作项目**新建一个项目，填写范围与目标。
4. 在**操作台**新建会话并与智能体协作；沙箱容器会按需自动创建，可在容器面板中使用终端、文件管理与 Caido。
5. 过程中产生的资产、发现、证据与攻击路径会沉淀到项目；结束后可查看可回放时间线与报告。
6. 高风险动作会被**红线策略**拦截并进入**策略审批**队列；所有关键动作可在**审计日志**中复核。

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

## 十、目录结构

```
ravenholt/
├── app.py / main.py / config.py / database.py    # 应用装配、入口、配置、数据库
├── core/            # 运行时核心：agent、会话池、策略引擎、strix 运行时、事件归档
├── service/ handler/ router/ schema/ model/       # 分层：逻辑 / 处理 / 路由 / 契约 / 模型
├── middleware/ utils/                             # 鉴权、统一响应等中间件与工具
├── strix/           # vendor 的 strix 运行时与技能库（由 .strix-vendor.json 校验）
├── sandbox/         # 沙箱镜像构建（Dockerfile / build.sh / 工具链技能）
├── web/             # 前端（src / dist-app 构建产物 / openapi.json）
├── docs/            # VitePress 文档站（en / zh）
├── scripts/         # 工具与自检脚本（export_schema、verify_*_selftest 等）
├── .ravenholt/      # 运行时配置：config.json / policy.yaml / skill_routes.yaml（均不入库）
├── setup.sh         # 一键部署脚本
├── start.sh         # 前台启动（打印管理员账号口令）
├── serve.sh         # 后台常驻服务管理
├── config-tool.sh   # LLM API Key 管理
├── docker-compose.prod.yml / .dev.yml
└── requirements.txt
```

## 十一、常见问题

**Q：启动即退出，日志显示策略相关报错？**
A：`.ravenholt/policy.yaml` 缺失或非法。平台对红线策略是 **fail-closed**，必须存在且合法：
`cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml`。

**Q：`npm run build` 失败？**
A：检查 Node 版本（需 ≥ 20.19）与 `web/node_modules` 是否残缺；删除 `web/node_modules` 后重跑 `npm install`。

**Q：页面还是旧内容？**
A：landing 等页面是**构建期固化**的 —— 改源码后必须重新 `cd web && npm run build`，再硬刷新浏览器（Ctrl+F5）。

**Q：无法创建沙箱容器？**
A：确认 Docker 守护进程在运行，且部署方式下平台进程能访问 Docker Socket（Compose 已挂载 `/var/run/docker.sock`）。

**Q：沙箱镜像构建失败？**
A：确认 x64 架构与足够磁盘；构建过程需联网下载 Ghidra / JADX 等工具链。

**Q：Docker 未安装可以运行吗？**
A：可以启动平台并使用控制面，但渗透/代码审计的沙箱执行面不可用。

**Q：Compose 部署后 app 连不上数据库？**
A：多半是复用了 `setup.sh` 生成的 `config.json`（随机库口令）与 Compose 固定口令 `123456` 不一致。见 [5.4](#54-docker-compose-部署) 的配置来源说明。

## 十二、许可

本项目基于 **MIT License** 发布，版权归 2026 `yv1ing` 与 `xiaoliuhua2`。详见 [LICENSE](./LICENSE)。

内部 vendor 的 strix 运行时按其原始许可（Apache-2.0）保留版权声明；使用本平台进行任何测试前，请确保已获得目标系统的明确授权。
