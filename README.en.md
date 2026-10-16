<div align="center">

<img src="docs/public/ravenholt-logo.png" alt="Ravenholt" width="120" />

# Ravenholt · Red-Team Multi-Agent Collaboration Platform

> An open-source, authorization-scoped red-team multi-agent platform for penetration testing, vulnerability discovery, code auditing, and security research

<a href="https://github.com/xiaoliuhua2/ravenholt"><img src="https://img.shields.io/badge/Release-v0.2.1-blue" alt="Version"></a>
<a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
<a href="https://xiaoliuhua2.github.io/ravenholt/"><img src="https://img.shields.io/badge/Docs-online-2ea44f" alt="Docs"></a>
<a href="./CHANGELOG.md"><img src="https://img.shields.io/badge/Changelog-CHANGELOG.md-6f42c1" alt="Changelog"></a>

<br/>

<img src="docs/public/images/landing.png" alt="Ravenholt landing page" width="880" />

[中文](./README.md) · **English** · [Online docs](https://xiaoliuhua2.github.io/ravenholt/)

</div>

---

> [!WARNING]
> **Authorized use only.** This project may be used for security testing, risk assessment, code auditing, and research **only within a legally authorized scope for which you hold explicit written permission**.
> It does not, and must not, grant any right to test, scan, access, or affect any unauthorized third-party system, network, service, account, or data. Unauthorized testing is illegal in most jurisdictions.
> **The authors are not responsible for any misuse or the damages it causes.**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Features](#2-features)
3. [Architecture](#3-architecture)
4. [Requirements](#4-requirements)
5. [Download & Installation](#5-download--installation)
6. [Configuration](#6-configuration)
7. [Running & Operations](#7-running--operations)
8. [Getting Started](#8-getting-started)
9. [UI Gallery](#9-ui-gallery)
10. [Project Layout](#10-project-layout)
11. [FAQ](#11-faq)
12. [License](#12-license)

---

## 1. Overview

Ravenholt is a **control-plane-oriented** red-team multi-agent platform: it turns agent-assisted security work into a **governed, reviewable** engineering process. Conversations are not the only source of truth — project scope, assets, findings, relationship graphs, attack paths, replayable timelines, and the agent's own reasoning process are all persisted as explicit application data.

At its core it uses [strix](https://github.com/usestrix/strix) as the penetration-testing execution engine (vendored in this repository, verified by `.strix-vendor.json`), and layers a control plane, a policy-governance layer, and an evidence plane on top of it:

| Part | Role |
| --- | --- |
| **strix runtime** (vendored) | Execution engine: agent orchestration, skill library, sandbox toolchain, Caido capture, reporting |
| **Platform control plane** (this repo) | Unified entry for sessions / projects / users / hosts / system config; REST + WebSocket; permission and resource boundaries |
| **Policy governance & evidence plane** | Red-line policy (fail-closed), action approvals, audit log, WorkProject evidence, replayable timelines |

## 2. Features

- **Playground**: multi-agent sessions, streaming chat, subagent panel, inline reasoning display, replayable timeline; the session column can be drag-resized and collapsed with one click.
- **Sandbox execution plane**: custom Docker sandbox containers providing a terminal, file management, noVNC remote view, and Caido capture/replay; containers are provisioned automatically per session.
- **WorkProject**: project metadata, owners, scope assets, sessions, records, relationship graph, and attack paths; findings carry evidence and impact.
- **Source-audit (white-box) channel**: upload a source archive to switch to the white-box track, with skill routing and prompts adjusted accordingly.
- **Egress proxies**: configuration and management of controlled network egress.
- **Policy approvals**: red-line policy decides whether an action is allowed; high-risk actions enter an approval queue for an admin to approve or reject.
- **Audit log**: auditable trail of key actions and events (action, verdict, block reason, etc.).
- **System users / System config**: accounts and role permissions, runtime parameters, and integration settings.
- **Replayable timeline**: all sources merged into a single ordered view for item-by-item post-mortem review.

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

## 4. Requirements

| Item | Requirement | Notes |
| --- | --- | --- |
| OS | **Linux x64** (Kali / Debian recommended) | Sandbox image is x64/amd64 only; arm64 unsupported |
| Python | **≥ 3.12** (3.13 recommended) | `venv` module required |
| Node.js | **≥ 20.19** (22+ recommended) | Required by Vite 8; the repo Dockerfile uses node:22 |
| PostgreSQL | **16+** | Data persistence |
| Docker | Recommended | Runtime for pentest/audit sandboxes; the execution plane is unavailable without it |
| Disk | ≥ 2 GB recommended (sandbox image needs 3+ GB more) | Sandbox image bundles Ghidra/Jadx and other toolchains |

## 5. Download & Installation

Three ways — pick one. **The one-command script is recommended for first-time deployment.**

### 5.1 Download the source

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git
cd ravenholt
```

> You can also download and unzip the ZIP archive. The repository vendors the complete `strix/` runtime and ships a **prebuilt frontend** under `web/dist-app`, so it is ready to use out of the box.

### 5.2 One-command deployment (recommended)

```bash
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

> [!IMPORTANT]
> The admin password is randomly generated and **printed only once** — save it immediately.
> If you lose it, delete `.ravenholt/config.json` and re-run `bash setup.sh` to regenerate it (the DB password is regenerated too, so the database role must be updated to match).

### 5.3 Manual step-by-step deployment

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
- `.ravenholt/skill_routes.yaml` (**optional**): an instance override layer for the skill routing table. When absent, the factory default is used (`core/strix_runtime/skill_routes.default.yaml`).

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

> [!NOTE]
> A prebuilt `web/dist-app` already ships in the repository, so you can skip this step to start the platform; rebuild only after changing frontend source.

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

### 5.4 Docker Compose deployment

For containerizing the control plane together with the database.

```bash
# Prerequisites: 1) .ravenholt/config.json and .ravenholt/policy.yaml are ready
#                   (a missing/invalid policy.yaml makes the platform fail-closed and refuse to start)
#                2) the sandbox-runtime:latest image has been built
docker compose -f docker-compose.prod.yml up -d --build
```

> The application image (`Dockerfile`) already ships the vendored `strix/` runtime and the built frontend `web/dist-app`, so nothing else needs to be mounted; `./.ravenholt` is mounted into the container by Compose as the runtime config.

> [!CAUTION]
> **Config source for Compose (important — don't mix it up)**: the bundled `postgres` service uses the fixed password `123456` (see `docker-compose.prod.yml`), which matches the repository's `.ravenholt/config.json.example`. For Compose, **copy the examples directly**:
>
> ```bash
> cp .ravenholt/config.json.example .ravenholt/config.json
> cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
> ```
>
> **Do not reuse the `config.json` generated by `bash setup.sh` (5.2)**: that script generates a **random DB password**, which does not match the Compose `postgres` password, so the app will fail to connect to the database and refuse to start.

The stack has three services:

| Service | Notes |
| --- | --- |
| `app` | Builds image `ravenholt:latest`; `network_mode: host`; mounts `./.ravenholt` and `/var/run/docker.sock` (to create sandbox containers) |
| `postgres` | `postgres:16-alpine`, data in `./.postgres-data` |
| `pgadmin` | <http://127.0.0.1:5433> for graphical DB access |

> Note: `app` uses host networking and mounts the Docker socket (it needs to create sandbox containers) — use it only on a trusted host.
> For development you can also start just the database with `docker compose -f docker-compose.dev.yml up -d`.

## 6. Configuration

### `.ravenholt/config.json`

| Section | Key fields | Notes |
| --- | --- | --- |
| `system` | `listen_addr` / `listen_port` | Listen address and port (default `0.0.0.0:8000`) |
| | `encrypt_key` | Data encryption key — **must be changed** to a ≥32-char random string |
| | `bootstrap_admin` | Admin auto-created on first start (`username` / `email` / `password`); log in with the email |
| `database` | `host` / `port` / `database` / `username` / `password` | PostgreSQL connection; for Compose, `host` is `127.0.0.1` |
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

## 7. Running & Operations

```bash
bash start.sh            # foreground (prints the admin account and password; Ctrl+C to stop)
bash serve.sh start      # background service (PID file, port health check, logs to disk)
bash serve.sh status     # show process / port / health check
bash serve.sh logs 40    # show startup log (-f to follow)
bash serve.sh restart    # restart
bash serve.sh stop       # stop (graceful SIGTERM)
```

> [!TIP]
> `bash start.sh` reads `.ravenholt/config.json` and prints the admin email and password to the screen for the first login; if `bootstrap_admin` is disabled it says so instead.

- Application log: `.ravenholt/app.log`
- Service log: `logs/serve.log`
- URL: <http://127.0.0.1:8000>; API docs: <http://127.0.0.1:8000/docs>

## 8. Getting Started

1. Open <http://127.0.0.1:8000> and log in with the admin email and password.

   <img src="docs/public/images/login.png" alt="Login page" width="820" />

2. Go to **System Config** and fill in the `agents` LLM API key (or set it beforehand with `config-tool.sh set`).
3. Go to **Work Projects**, create a project, and fill in scope and targets.
4. In the **Playground**, start a session and work with the agents; sandbox containers are created on demand, and you can use the terminal, file manager, and Caido from the container panel.
5. Assets, findings, evidence, and attack paths produced along the way are retained in the project; afterwards you can review the replayable timeline and reports.
6. High-risk actions are blocked by the **red-line policy** and routed to the **Policy Approvals** queue; every key action can be reviewed in the **Audit Log**.

## 9. UI Gallery

| Playground | Work Projects |
| --- | --- |
| <img src="docs/public/images/playground.png" alt="Playground" width="420" /> | <img src="docs/public/images/work-projects.png" alt="Work Projects" width="420" /> |

| System Config | System Users |
| --- | --- |
| <img src="docs/public/images/system-config.png" alt="System Config" width="420" /> | <img src="docs/public/images/system-users.png" alt="System Users" width="420" /> |

| Policy Approvals | Audit Log |
| --- | --- |
| <img src="docs/public/images/policy-confirmations.png" alt="Policy Approvals" width="420" /> | <img src="docs/public/images/audit-events.png" alt="Audit Log" width="420" /> |

| Egress Proxies | Landing page |
| --- | --- |
| <img src="docs/public/images/egress-proxies.png" alt="Egress Proxies" width="420" /> | <img src="docs/public/images/landing.png" alt="Landing page" width="420" /> |

## 10. Project Layout

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
├── start.sh         # foreground start (prints admin account & password)
├── serve.sh         # background service management
├── config-tool.sh   # LLM API key management
├── docker-compose.prod.yml / .dev.yml
└── requirements.txt
```

## 11. FAQ

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

**Q: After Compose deployment the app cannot connect to the database?**
A: Most likely you reused the `config.json` generated by `setup.sh` (random DB password), which does not match the Compose fixed password `123456`. See the config-source note in [5.4](#54-docker-compose-deployment).

## 12. License

Released under the **MIT License**, copyright 2026 `yv1ing` and `xiaoliuhua2`. See [LICENSE](./LICENSE).

The vendored strix runtime retains its original license (Apache-2.0) and copyright notices. Before running any test with this platform, make sure you have explicit authorization for the target.
