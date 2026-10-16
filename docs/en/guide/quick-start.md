---
title: Quick Start
editLink: true
---

# Quick Start

Ravenholt's core philosophy is to pursue extreme simplicity as much as possible, so Ravenholt's deployment also keeps the steps as simple as possible.

> :warning: Iteration Notice
>
> Ravenholt is currently in a phase of rapid iteration and may undergo major structural or contract changes. To ensure code quality, forward compatibility is not considered for now. When using it in production, proper version control is recommended, and historical data may require additional migration measures.

## Before You Start

### Basic Configuration

Ravenholt requires only the following core content and infrastructure to run:

| Item | Description |
| --- | --- |
| `.ravenholt/config.json` | System runtime configuration |
| `.ravenholt/policy.yaml` | Red-line policy (**fail-closed**: missing or invalid will cause the platform to refuse to start) |
| `Docker` | Runtime for the sandbox environment (penetration/audit execution depends on it) |
| `PostgreSQL` | Persistent data storage |
| `Sandbox` | Customized sandbox image `sandbox-runtime:latest` |

Get the latest code from GitHub:

```bash
git clone https://github.com/xiaoliuhua2/ravenholt.git && cd ravenholt
```

### One-Click Deployment (Recommended)

The project ships with a one-click deployment script covering "environment check → system dependencies → configuration initialization → database → Python dependencies → frontend build → sandbox image → self-check":

```bash
# Check only, without modifying any files
bash setup.sh --check

# Check + install + deploy
bash setup.sh
```

The script generates `.ravenholt/config.json` (a random `encrypt_key`, database password, and administrator password — **the administrator password is printed only once, so save it immediately**) and `policy.yaml`. For details, see the [installation section of the README](https://github.com/xiaoliuhua2/ravenholt#五安装部署).

### Build the Sandbox

Ravenholt's capabilities are deeply tied to the sandbox environment, so you need to build the corresponding sandbox image:

> :warning: Architecture Limitation
>
> The sandbox image build currently supports only the x64/amd64 architecture. arm64/Apple Silicon, including Apple Silicon Macs, is not supported. Run this step on an x64 host or in an x64 build environment.

```bash
cd sandbox && bash build.sh
```

After a short wait, you will get `sandbox-runtime:latest`. The runtime provisions the image record automatically per session, so there is **no need** to add it manually in the system.

## Production Environment

When deploying to production, follow these steps one by one.

### Prepare Configuration

```bash
cp .ravenholt/config.json.example .ravenholt/config.json
cp .ravenholt/policy.yaml.example .ravenholt/policy.yaml
```

Edit the system runtime configuration in `.ravenholt/config.json`, mainly updating the following items:

| Item | Description |
| --- | --- |
| `system.encrypt_key` | System data encryption key. This must be changed. A random string of at least 32 bytes is recommended. |
| `system.bootstrap_admin` | Default system administrator information. This must be changed; a strong password is recommended (the email is used for login). |
| `database` | System database connection information. When deploying with Docker Compose, set `host` to the corresponding service name. |
| `agents.*` | LLM API configuration for each agent. Different providers and models can be configured separately as needed. |

> `.ravenholt/policy.yaml` is the **red-line policy**, and the platform is fail-closed toward it: a missing file, a YAML syntax error, or a validation failure will all **refuse to start**; the `enabled` flags of the `rate_limit`, `sandbox`, `kill_switch`, and `audit` sections must all be `true`.

### Start Containers

Once everything is ready, start Ravenholt with one command:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

### Reverse Proxy (Optional)

By default, the service listens on `0.0.0.0:8000`. You can configure it to listen on `127.0.0.1:8000` as needed and set up a reverse proxy.

An example Nginx configuration is shown below:

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

## Development Environment

When deploying in a development environment, follow these steps one by one.

### Configure the Environment

- Python version: 3.13.5
- Node.js version: 24.16.0

Create a virtual environment with the following commands:

```bash
python -m venv .venv

# Windows:
.venv\Scripts\Activate.ps1

# Linux:
source .venv/bin/activate
```

Install system dependencies:

```bash
pip install -r requirements.txt
```

```bash
cd web && npm install
```

Build the frontend project:

```bash
cd web && npm run build
```

Create the database:

Use `docker-compose.dev.yml` to start the database environment with one command:

```bash
docker compose -f docker-compose.dev.yml up -d
```

Visit `127.0.0.1:5433`, log in with the configured pgAdmin username and password, enter the PostgreSQL connection information, and connect to the service.

Create the `ravenholt` database. The database name must match the value configured in `config.json`.

### Start the Project

Create `.ravenholt/config.json` and `.ravenholt/policy.yaml`, filling in the relevant information based on the corresponding `.example` files.

Start the project with the following command:

```bash
# Background daemon (recommended; prints the admin account and password on start)
bash serve.sh start

# Other subcommands
bash serve.sh run      # foreground (debug; Ctrl+C to stop)
bash serve.sh status   # show process / port / health check
bash serve.sh logs 40  # show log (-f to follow)
bash serve.sh restart  # restart
bash serve.sh stop     # stop (graceful SIGTERM)
```

By default, the service listens on `0.0.0.0:8000`. Visit `http://127.0.0.1:8000/` to access it.

> Tip: the frontend pages are **fixed at build time** — after changing `web/src` you must re-run `cd web && npm run build` and then hard-refresh the browser.

## Next Step

Follow the instructions in [First Use](./first-use) to officially start working with Ravenholt.
