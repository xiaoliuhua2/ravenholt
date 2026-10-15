<div align="center">

<img src="docs/public/ravenholt-logo.png" alt="Ravenholt" width="120" />

# Ravenholt · Red-Team Multi-Agent Collaboration Platform

> An open-source, authorization-scoped red-team multi-agent platform for penetration testing, vulnerability discovery, code auditing, and security research

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-v0.2.1-blue.svg)](./CHANGELOG.md)
[![Docs](https://img.shields.io/badge/docs-online-2ea44f.svg)](https://xiaoliuhua2.github.io/ravenholt/)

[中文](./README.md) · **English**

</div>

Ravenholt uses [strix](https://github.com/usestrix/strix) as its penetration-testing execution engine (vendored in this repository, verified by `.strix-vendor.json`), and layers a control plane, a policy-governance layer, and an evidence plane on top of it: multi-agent orchestration, Docker sandbox execution, red-line policy approvals, audit logging, WorkProject evidence retention, and replayable timelines.

- License: MIT (see [LICENSE](./LICENSE))
- Changelog: [CHANGELOG.md](./CHANGELOG.md)
- Documentation: <https://xiaoliuhua2.github.io/ravenholt/>
- Repository: <https://github.com/xiaoliuhua2/ravenholt>

---

> ### Security Notice
>
> This project is intended **only** for security testing, risk assessment, code auditing, and research within legally authorized scope.
> It grants no permission to test, scan, access, or affect any third-party system, network, service, account, or data.
> **The authors are not responsible for any misuse or the damages it causes.**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Architecture](#3-architecture)
4. [Requirements](#4-requirements)
5. [Installation](#5-installation)
6. [Configuration](#6-configuration)
7. [Running & Operations](#7-running--operations)
8. [Getting Started](#8-getting-started)
9. [Project Layout](#9-project-layout)
10. [FAQ](#10-faq)
11. [License](#11-license)

---

## 1. Overview

Ravenholt is a **control-plane-oriented** red-team multi-agent platform: it turns agent-assisted security work into a **governed, reviewable** engineering process. Conversations are not the only source of truth — project scope, assets, findings, relationship graphs, attack paths, replayable timelines, and the agent's own reasoning process are all persisted as explicit application data.

Three parts make up the platform:

| Part | Role |
| --- | --- |
| **strix runtime** (vendored) | Execution engine: agent orchestration, skill library, sandbox toolchain, Caido capture, reporting |
| **Platform control plane** (this repo) | Unified entry for sessions / projects / users / hosts / system config; REST + WebSocket; permission and resource boundaries |
| **Policy governance & evidence plane** | Red-line policy (fail-closed), action approvals, audit log, WorkProject evidence, replayable timelines |

![Ravenholt landing page](docs/public/images/landing.png)

![Playground](docs/public/images/playground.png)

![Work Projects](docs/public/images/work-projects.png)

---

## 2. Features

- **Playground**: multi-agent sessions, streaming chat, subagent panel, inline reasoning display, replayable timeline.
- **Sandbox execution plane**: custom Docker sandbox containers providing a terminal, file management, noVNC remote view, and Caido capture/replay; containers are provisioned automatically per session.
- **WorkProject**: project metadata, owners, scope assets, sessions, records, relationship graph, and attack paths; findings carry evidence and impact.
- **Source-audit (white-box) channel**: upload a source archive to switch to the white-box track, with skill routing and prompts adjusted accordingly.
- **Egress proxies**: configuration and management of controlled network egress.
- **Policy approvals**: red-line policy decides whether an action is allowed; high-risk actions enter an approval queue for an admin to approve or reject.
- **Audit log**: auditable trail of key actions and events (action, verdict, block reason, etc.).
- **System users / System config**: accounts and role permissions, runtime parameters, and integration settings.
- **Replayable timeline**: all sources merged into a single ordered view for item-by-item post-mortem review.

---

## 3. Architecture

```
┌──────────────────────────────────────────────┐
│  Web console (React 19 + Semi UI + Vite)      │
│  Landing · Login · Playground · Projects · …  │
└───────────────────────┬──────────────────────┘
                        │ REST + WebSocket
┌───────────────────────▼──────────────────────┐
│  Control plane (FastAPI, /api)                │
│  Users · Sessions · Projects · Policy · Audit │
└───────┬───────────────────────┬──────────────┘
        │                       │
┌───────▼────────┐      ┌───────▼──────────────┐
│ Session        │      │ Evidence plane        │
│ runtime        │      │ (WorkProject)         │
│ strix engine   │      │ assets/findings/graph │
│ dynamic agents │      │ evidence + verifier   │
└───────┬────────┘      └──────────────────────┘
        │
┌───────▼──────────────────────────────────────┐
│  Sandbox execution plane (Docker)             │
│  sandbox-runtime image · toolchain · Caido    │
└───────┬──────────────────────────────────────┘
        │
┌───────▼──────────┐
│  PostgreSQL 16   │
└──────────────────┘
```

**Tech stack**

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite 8, Semi UI, CodeMirror, xterm, Cytoscape, Mermaid |
| Backend | Python 3.13, FastAPI, SQLModel/SQLAlchemy, asyncpg, Uvicorn, WebSocket |
| Execution engine | strix (vendored), Docker sandbox, Caido, Kali toolchain |
| Database | PostgreSQL 16 |
| Deployment | venv (direct) / Docker Compose |

---

## 4. Requirements

| Item | Requirement | Notes |
| --- | --- | --- |
| OS | **Linux x64** (Kali / Debian recommended) | Sandbox image is x64/amd64 only; arm64 unsupported |
| Python | **≥ 3.12** (3.13 recommended) | `venv` module required |
| Node.js | **≥ 20.19** (22+ recommended) | Required by Vite 8; the repo Dockerfile uses node:22 |
| PostgreSQL | **16+** | Data persistence |
| Docker | Recommended | Runtime for pentest/audit sandboxes; the execution plane is unavailable without it |
| Disk | ≥ 2 GB recommended (sandbox image needs 3+ GB more) | Sandbox image bundles Ghidra/Jadx and other toolchains |

---

## 5. Installation

Three ways — pick one. **The one-command script is recommended for first-time deployment.**

### 5.1 One-command deployment (recommended)

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git
cd ravenholt

# 1) Preflight: check the environment only, no files are modified
bash setup.sh --check

# 2) Deploy: check -> install system deps -> init config -> create DB
#    -> install Python deps -> build frontend -> self-check
bash setup.sh

# Optional: also build the pentest sandbox image (large download, slow)
bash setup.sh --with-sandbox
```

The script runs in 8 stages, printing results as it goes:

| Stage | What it does |
| --- | --- |
| 1/8 Environment check | OS/arch/Python/Node/Docker/PostgreSQL/permissions/port/disk, each with a verdict and a fix command |
| 2/8 System deps | Installs whatever is missing via apt, then re-checks hard requirements such as Python/venv |
| 3/8 Config init | Generates `.ravenholt/config.json` (random `encrypt_key`, DB password, admin password) and **`policy.yaml`** |
| 4/8 PostgreSQL | Starts the service, creates the role and database, aligns the password with config.json |
| 5/8 Python deps | Creates `.venv` and runs `pip install -r requirements.txt` |
| 6/8 Frontend build | `npm install` + `npm run build` under `web/`, producing `web/dist-app` |
| 7/8 Sandbox image | Detects Docker/arch; prompts, or builds automatically with `--with-sandbox` |
| 8/8 Post-install self-check | Bytecode compile, config/policy load, `create_app` assembly smoke test |

The script is **idempotent**: existing `config.json` / `policy.yaml` are never overwritten.

> **Important**: the admin password is randomly generated and **printed only once** — save it immediately.
> If you lose it, delete `.ravenholt/config.json` and re-run `bash setup.sh` to regenerate it (the DB password is regenerated too, so the database role must be updated to match).

### 5.2 Manual step-by-step deployment

For environments where you want to control each step.

**Step 1: System dependencies**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
                    postgresql postgresql-client \
                    curl openssl ca-certificates
# Node.js (versions shipped by Debian/Kali are often too old; use nodesource)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
# Docker (optional; needed by the sandbox execution plane)
sudo apt install -y docker.io && sudo systemctl enable --now docker
```

Verify: `python3 -V` (≥3.12), `node -v` (≥20.19), `psql --version`, `docker -v`.

**Step 2: Database**

```bash
sudo systemctl start postgresql
sudo -u postgres psql -c "CREATE USER root WITH PASSWORD 'your-db-password';"
sudo -u postgres psql -c "CREATE DATABASE ravenholt OWNER root;"
```

> The password must match `database.password` in `config.json` in step 3.

**Step 3: Configuration files (important, don't skip)**

```bash
cp .ravenholt/config.json.example .ravenholt/config.json
cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
```

- `.ravenholt/config.json`: edit `system.encrypt_key` (≥32 random chars, required), `system.bootstrap_admin` (admin email and a strong password), `database` (`host=127.0.0.1` for a local DB), and `agents.*` (LLM `api_key` / `base_url` / `model`).
- `.ravenholt/policy.yaml`: the **red-line policy, fail-closed** — if the file is missing, the YAML is invalid, or validation fails, the platform **refuses to start**. The `enabled` flag of the `rate_limit`, `sandbox`, `kill_switch`, and `audit` sections must be `true`.
- `.ravenholt/skill_routes.yaml` (**optional**): an instance override layer for the skill routing table. When absent, the factory default is used (`core/strix_runtime/skill_routes.default.yaml`). To customize: `cp .ravenholt/skill_routes.yaml.example .ravenholt/skill_routes.yaml` and edit.

**Step 4: Python dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Step 5: Frontend build**

```bash
cd web
npm install
npm run build      # runs generate:api -> tsc -> vite build
cd ..
```

This produces `web/dist-app`, which the backend serves automatically.

**Step 6: Sandbox image (optional; needed by the execution plane)**

```bash
cd sandbox && bash build.sh      # produces sandbox-runtime:latest (x64 only)
cd ..
```

Sandbox containers are provisioned automatically per session, and the image record is created on first use — no manual registration needed.

**Step 7: Start**

```bash
python main.py                   # foreground (Ctrl+C to stop)
# or as a background service:
bash serve.sh start
```

Open <http://127.0.0.1:8000>.

### 5.3 Docker Compose deployment

For containerizing the control plane together with the database.

```bash
# Prerequisites: 1) .ravenholt/config.json and .ravenholt/policy.yaml are ready
#                2) the sandbox-runtime:latest image has been built
docker compose -f docker-compose.prod.yml up -d --build
```

The stack has three services:

| Service | Notes |
| --- | --- |
| `app` | Builds image `ravenholt:latest`; `network_mode: host`; mounts `./.ravenholt` and `/var/run/docker.sock` (to create sandbox containers) |
| `postgres` | `postgres:16-alpine`, data in `./.postgres-data` |
| `pgadmin` | <http://127.0.0.1:5433> for graphical DB access |

> Note: `app` uses host networking and mounts the Docker socket (it needs to create sandbox containers) — use it only on a trusted host.
> For development you can also start just the database with `docker compose -f docker-compose.dev.yml up -d`.

---

## 6. Configuration

### `.ravenholt/config.json`

| Section | Key fields | Notes |
| --- | --- | --- |
| `system` | `listen_addr` / `listen_port` | Listen address and port (default `0.0.0.0:8000`) |
| | `encrypt_key` | Data encryption key — **must be changed** to a ≥32-char random string |
| | `bootstrap_admin` | Admin auto-created on first start (`username` / `email` / `password`); log in with the email |
| `database` | `host` / `port` / `database` / `username` / `password` | PostgreSQL connection; for Compose, `host` is the service name |
| `agent_runtime` | `main_max_turns` / context-compaction settings | Turn limits and context compaction thresholds |
| `agent_pool` | `max_size` / `ttl_seconds` | Agent session pool |
| `agents` | `cso` … | Per-agent LLM config: `api_key` / `base_url` / `model` / `context_window` |
| `integrations` | `web_search_provider`, etc. | Web-search backends (e.g. SearXNG / Exa / Perplexity) |

> The agent list is determined by the `agents` section of this config (by default only the `cso` preset), not by a fixed static roster.

### Managing LLM API keys

```bash
bash config-tool.sh list                                  # show a summary of every agent config
bash config-tool.sh set sk-xxxx --url https://api.deepseek.com/v1 --model deepseek-v4-flash
bash config-tool.sh clear                                 # clear all keys
```

### Policy and skill routing

- `.ravenholt/policy.yaml`: the red-line policy (fail-closed). Changes made in the console take effect immediately and are written back to this file.
- `.ravenholt/skill_routes.yaml`: instance override layer for skill routing (optional).

---

## 7. Running & Operations

```bash
bash start.sh            # foreground (Ctrl+C to stop)
bash serve.sh start      # background service (PID file, port health check, logs to disk)
bash serve.sh status     # show process / port / health check
bash serve.sh logs 40    # show startup log (-f to follow)
bash serve.sh restart    # restart
bash serve.sh stop       # stop (graceful SIGTERM)
```

- Application log: `.ravenholt/app.log`
- Service log: `logs/serve.log`
- URL: <http://127.0.0.1:8000>; API docs: <http://127.0.0.1:8000/docs>

---

## 8. Getting Started

1. Open <http://127.0.0.1:8000> and log in with the admin email and password.
2. Go to **System Config** and fill in the `agents` LLM API key (or set it beforehand with `config-tool.sh set`).
3. Go to **Work Projects**, create a project, and fill in scope and targets.
4. In the **Playground**, start a session and work with the agents; sandbox containers are created on demand, and you can use the terminal, file manager, and Caido from the container panel.
5. Assets, findings, evidence, and attack paths produced along the way are retained in the project; afterwards you can review the replayable timeline and reports.
6. High-risk actions are blocked by the **red-line policy** and routed to the **Policy Approvals** queue; every key action can be reviewed in the **Audit Log**.

---

## 9. Project Layout

```
ravenholt/
├── app.py / main.py / config.py / database.py    # app assembly, entrypoint, config, DB
├── core/            # runtime core: agents, session pool, policy engine, strix runtime, event archiving
├── service/ handler/ router/ schema/ model/       # layers: logic / handling / routing / contracts / models
├── middleware/ utils/                             # auth, unified response, and other middleware/helpers
├── strix/           # vendored strix runtime and skill library (verified by .strix-vendor.json)
├── sandbox/         # sandbox image build (Dockerfile / build.sh / toolchain skills)
├── web/             # frontend (src / dist-app build output / openapi.json)
├── docs/            # VitePress documentation site (en / zh)
├── scripts/         # tooling and self-test scripts (export_schema, verify_*_selftest, etc.)
├── .ravenholt/      # runtime config: config.json / policy.yaml / skill_routes.yaml (all untracked)
├── setup.sh         # one-command deployment script
├── start.sh         # foreground start
├── serve.sh         # background service management
├── config-tool.sh   # LLM API key management
├── docker-compose.prod.yml / .dev.yml
└── requirements.txt
```

---

## 10. FAQ

**Q: It exits right after startup and the log mentions policy errors?**
A: `.ravenholt/policy.yaml` is missing or invalid. The platform is **fail-closed** on the red-line policy, so the file must exist and be valid:
`cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml`.

**Q: `npm run build` fails?**
A: Check the Node version (≥ 20.19) and whether `web/node_modules` is incomplete; delete `web/node_modules` and re-run `npm install`.

**Q: The page still shows old content?**
A: The landing page and friends are **frozen at build time** — after changing source you must re-run `cd web && npm run build` and then hard-refresh the browser (Ctrl+F5).

**Q: Cannot create sandbox containers?**
A: Make sure the Docker daemon is running and that the platform process can access the Docker socket (Compose mounts `/var/run/docker.sock`).

**Q: The sandbox image build fails?**
A: Check the x64 architecture and available disk space; the build downloads toolchains such as Ghidra / JADX.

**Q: Can it run without Docker?**
A: Yes — the control plane starts and works, but the pentest/code-audit sandbox execution plane is unavailable.

---

## 11. License

Released under the **MIT License**, copyright 2026 `yv1ing` and `xiaoliuhua2`. See [LICENSE](./LICENSE).

The vendored strix runtime retains its original license (Apache-2.0) and copyright notices. Before running any test with this platform, make sure you have explicit authorization for the target.
