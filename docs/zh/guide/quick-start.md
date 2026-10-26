---
title: 快速开始
editLink: true
---

# 快速开始

Ravenholt 的核心理念是：尽力做到极致的简洁，因此 Ravenholt 的部署也将尽力简化步骤。

> :warning: 迭代说明
>
> 目前，Ravenholt 正处于快速迭代阶段，可能出现大幅度的结构、契约变动。为了保证代码质量，暂不考虑向前兼容。在生产环境使用时，建议做好合理的版本控制，历史数据可能需要额外的迁移措施。

## 开始之前

### 基础配置

Ravenholt 的运行只需要以下核心内容和基础设施：

| 项目 | 说明 |
| --- | --- |
| `.ravenholt/config.json` | 系统的运行时配置 |
| `.ravenholt/policy.yaml` | 红线策略（**fail-closed**：缺失或非法会导致平台拒绝启动） |
| `Docker` | 沙盒环境的运行时（渗透/审计执行依赖它） |
| `PostgreSQL` | 数据持久化存储 |
| `Sandbox` | 一体化沙盒镜像 `sandbox-runtime:latest`（由 `sandbox/build.sh` 构建；上游镜像可作降级选项） |

通过 GitHub 获取最新代码：

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git && cd ravenholt
```

### 一键部署（推荐）

项目自带一键部署脚本，覆盖「环境检测 → 系统依赖 → 配置初始化 → 数据库 → Python 依赖 → 前端构建 → 沙箱镜像 → 自检」：

```bash
# 只体检，不改动任何文件
bash setup.sh --check

# 检测 + 安装 + 部署（完整功能：含一体化沙盒镜像）
bash setup.sh --with-sandbox
```

脚本会生成 `.ravenholt/config.json`（随机 `encrypt_key`、数据库口令、管理员口令——**管理员口令只打印一次，请立即保存**）与 `policy.yaml`。详细说明见 [README 的安装章节](https://github.com/xiaoliuhua2/ravenholt#五安装部署)。

### 构建沙盒（完整功能）

Ravenholt 的沙盒镜像 `sandbox-runtime:latest` **以 strix 上游镜像为基础**，在其上叠加定制工具链（Ghidra / Jadx / apktool / binwalk / observer_ward / agent-browser / hurl）、容器内 Go 控制面与技能资源 `.agents/skills`。因此它同时服务两种用途：**agent 会话沙箱**（含 Caido 抓包）与**平台「沙箱容器」的人工控制台**（终端 / 文件 / noVNC / egress 动态刷新）。

> :warning: 架构限制
>
> Sandbox 镜像构建目前仅支持 x64/amd64 架构，不支持 arm64/Apple Silicon（包括 Apple Silicon Mac）。请在 x64 主机或 x64 构建环境中执行该步骤。

```bash
cd sandbox && bash build.sh
```

脚本默认经 `https://gh-proxy.com/` 拉取 GitHub Releases（国内直连 `github.com` 的 release 资产常被中途 RST，表现为 `curl: (35) Recv failure: Connection reset by peer`）。需要更换通道时用环境变量覆盖：

```bash
cd sandbox && GITHUB_MIRROR=https://ghfast.top/ bash build.sh
```

稍等片刻即可得到 `sandbox-runtime:latest`。构建完成后，**让会话真正使用它**：在 `.ravenholt/config.json` 里设置 `sandbox.image`（用 `bash setup.sh --with-sandbox` 部署时这一步会自动完成）：

```json
"sandbox": {
    "network": "ravenholt-lan",
    "image": "sandbox-runtime:latest"
}
```

另外，若要在控制台「沙箱容器」页创建带终端 / 文件 / noVNC 的容器，还需在**「沙箱镜像」页新增一条记录**（`image_name` 填 `sandbox-runtime:latest`，`Control Port` 填 `8000`）。

> **不构建也能渗透**：此时会话使用上游镜像 `ghcr.io/usestrix/strix-sandbox:1.3.0`（含 Caido 与 Kali 工具链，首次会话自动拉取），只是缺少上述定制工具与容器控制台。

## 生产环境

生产环境部署时，请按照以下步骤逐项进行。

### 准备配置

```bash
cp .ravenholt/config.json.example .ravenholt/config.json
cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
```

编辑 `.ravenholt/config.json` 中的系统运行时配置，主要修改以下内容：

| 项目 | 说明 |
| --- | --- |
| `system.encrypt_key` | 系统数据加密密钥，必须修改，建议使用至少 32 字节的随机字符串。 |
| `system.bootstrap_admin` | 系统默认管理员信息，必须修改，建议使用强密码（登录用邮箱）。 |
| `database` | 系统数据库连接信息，使用 Docker Compose 部署时，`host` 填写对应的服务名称。 |
| `agents.*` | 各智能体的 LLM API 配置，可根据需要分别配置不同的供应商和模型。 |

> `.ravenholt/policy.yaml` 是**红线策略**，平台对它 fail-closed：文件缺失 / YAML 语法错误 / 校验失败都会**拒绝启动**；`rate_limit`、`sandbox`、`kill_switch`、`audit` 四节的 `enabled` 必须为 `true`。

### 启动容器

一切准备就绪后，使用以下命令一键启动 Ravenholt：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### 反向代理（可选）

服务默认监听在 `0.0.0.0:8000` 上，可根据需要设置监听在 `127.0.0.1:8000`，并配置反向代理。

可参考的 Nginx 配置如下：

```text
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 10000 ssl default_server;

    ssl_certificate     /etc/nginx/ssl/vps.crt;
    ssl_certificate_key /etc/nginx/ssl/vps.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    auth_basic "Origin Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

## 开发环境

开发环境部署时，请按照以下步骤逐项进行。

### 配置环境

- Python 版本：3.13.5
- Node.js 版本：24.16.0

使用以下命令创建虚拟环境：

```bash
python -m venv .venv

# Windows:
.venv\Scripts\Activate.ps1

# Linux:
source .venv/bin/activate
```

安装系统依赖：

```bash
pip install -r requirements.txt
```

```bash
cd web && npm install
```

构建前端项目：

```bash
cd web && npm run build
```

创建数据库：

使用 `docker-compose.dev.yml` 一键启动数据库环境：

```bash
docker compose -f docker-compose.dev.yml up -d
```

访问 `127.0.0.1:5433`，使用设置的 pgAdmin 账号密码登录，填写 PostgreSQL 连接信息并连接到服务。

创建 `ravenholt` 数据库，数据库名称要与 `config.json` 中填写的保持一致。

### 启动项目

创建 `.ravenholt/config.json` 与 `.ravenholt/policy.yaml`，根据对应的 `.example` 文件填写相关信息。

使用以下命令启动项目：

```bash
# 后台常驻（推荐；启动时打印管理员账号与口令）
bash serve.sh start

# 其余子命令
bash serve.sh run      # 前台运行（调试用，Ctrl+C 停止）
bash serve.sh status   # 查看进程 / 端口 / 健康检查
bash serve.sh logs 40  # 查看日志（-f 持续跟踪）
bash serve.sh restart  # 重启
bash serve.sh stop     # 停止（SIGTERM 优雅退出）
```

服务默认监听在 `0.0.0.0:8000` 上，使用 `http://127.0.0.1:8000/` 即可访问。

> 提示：前端页面是**构建期固化**的——修改 `web/src` 后必须重新 `cd web && npm run build`，再硬刷新浏览器。

## 下一步

根据 [首次使用](./first-use) 中的说明，正式开启 Ravenholt 的工作！
