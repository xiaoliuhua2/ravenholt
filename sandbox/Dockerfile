# syntax=docker/dockerfile:1
#
# ============================================================
# Ravenholt 一体化沙箱镜像
#
# 以 strix 上游镜像（自带 Caido + Kali 工具链）为基础，叠加 Ravenholt 的定制能力：
#   - Ghidra / Jadx / apktool / binwalk / observer_ward / agent-browser-cli
#   - 容器内 Go 控制面 sandbox-proxy（终端 / 文件 / noVNC 转发 / egress 动态刷新）
#   - 容器内技能资源 .agents/skills（平台的 load_skill 按 /workspace/.agents/skills 解析）
#   - 桌面栈 Xvfb + x11vnc + noVNC、tor
#
# 于是同一个镜像既能当「会话沙箱」（agent 执行面，含 Caido 抓包）也能当
# 「平台沙箱容器」（人工控制台），不需要在两个镜像之间取舍。
#
# 构建：bash build.sh
# 换基础镜像：docker build --build-arg STRIX_SANDBOX_IMAGE=... -t sandbox-runtime:latest .
# ============================================================

ARG STRIX_SANDBOX_IMAGE=ghcr.io/usestrix/strix-sandbox:1.3.0

# GitHub Releases 下载加速前缀。本验证环境直连 github.com 的 release 资产会被
# 中途 RST（curl: (35) Recv failure: Connection reset by peer），构建因此中断。
# 留空 = 直连；可填任一前缀式代理，如 https://gh-proxy.com/ 或 https://ghfast.top/ 。
# 用法：docker build --build-arg GITHUB_MIRROR=https://gh-proxy.com/ -t sandbox-runtime:latest .
ARG GITHUB_MIRROR=

ARG AGENT_BROWSER_VERSION=0.3.4
ARG GHIDRA_VERSION=12.1
ARG GHIDRA_BUILD=20260513
ARG JADX_VERSION=1.5.5
ARG OBSERVER_WARD_VERSION=2026.4.8

# ---------- 容器内 Go 控制面 ----------
FROM golang:1.26-trixie AS proxy-builder

ENV CGO_ENABLED=0

WORKDIR /src/proxy
COPY proxy/ ./
RUN go build -trimpath -ldflags='-s -w' -o /sandbox-proxy .

# ---------- uv（供容器内工具安装用） ----------
FROM ghcr.io/astral-sh/uv:latest AS uv-bin

# ---------- agent-browser ----------
FROM debian:trixie-slim AS agent-browser-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG AGENT_BROWSER_VERSION
ARG GITHUB_MIRROR

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl tar unzip; \
    mkdir -p \
      /opt/agent-browser/bin \
      /opt/agent-browser/chrome-extension \
      /tmp/agent-browser-cli \
      /tmp/agent-browser-extensions; \
    curl -fsSL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 "${GITHUB_MIRROR}https://github.com/sleepinginsummer/agent-browser-cli/releases/download/v${AGENT_BROWSER_VERSION}/chrome-extensions.zip" -o /tmp/chrome-extensions.zip; \
    unzip -q /tmp/chrome-extensions.zip -d /tmp/agent-browser-extensions; \
    extension_dir="$(find /tmp/agent-browser-extensions -type f -name manifest.json -printf '%h\n' | sort | head -n 1)"; \
    test -n "$extension_dir"; \
    echo "agent-browser extension dir: $extension_dir"; \
    cp -a "$extension_dir"/. /opt/agent-browser/chrome-extension; \
    test -f /opt/agent-browser/chrome-extension/manifest.json; \
    curl -fsSL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 "${GITHUB_MIRROR}https://github.com/sleepinginsummer/agent-browser-cli/releases/download/v${AGENT_BROWSER_VERSION}/sleepinsummer-agent-browser-cli-linux-x64-${AGENT_BROWSER_VERSION}.tgz" -o /tmp/agent-browser-cli.tgz; \
    tar -xzf /tmp/agent-browser-cli.tgz -C /tmp/agent-browser-cli; \
    cp /tmp/agent-browser-cli/package/bin/agent-browser-cli /opt/agent-browser/bin/agent-browser-cli; \
    chmod 755 /opt/agent-browser/bin/agent-browser-cli; \
    /opt/agent-browser/bin/agent-browser-cli --help >/dev/null; \
    find /opt/agent-browser/chrome-extension -type f \( \
      -name '*.md' -o \
      -name '*.map' \
    \) -delete; \
    rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/* /var/cache/apt/*

# ---------- Ghidra ----------
FROM debian:trixie-slim AS ghidra-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG GHIDRA_VERSION
ARG GHIDRA_BUILD
ARG GITHUB_MIRROR
ARG GHIDRA_URL=https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_${GHIDRA_VERSION}_build/ghidra_${GHIDRA_VERSION}_PUBLIC_${GHIDRA_BUILD}.zip

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends binutils ca-certificates curl unzip; \
    curl -fsSL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 "${GITHUB_MIRROR}${GHIDRA_URL}" -o /tmp/ghidra.zip; \
    unzip -q /tmp/ghidra.zip -d /opt; \
    ghidra_dir="$(find /opt -maxdepth 1 -type d -name 'ghidra_*_PUBLIC' | sort | head -n 1)"; \
    test -n "$ghidra_dir"; \
    mv "$ghidra_dir" /opt/ghidra; \
    find /opt/ghidra -type d \( \
      -name '.git' -o \
      -name '__pycache__' -o \
      -name 'docs' -o \
      -name 'GPL' \
    \) -prune -exec rm -rf '{}' +; \
    find /opt/ghidra -type f \( \
      -name '*.md' -o \
      -name '*.pdb' -o \
      -name '*.src.zip' \
    \) -delete; \
    find /opt/ghidra -type f -name '*.so' -exec strip --strip-unneeded '{}' + 2>/dev/null || true; \
    rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/* /var/cache/apt/*

# ---------- Jadx ----------
FROM debian:trixie-slim AS jadx-builder

ARG DEBIAN_FRONTEND=noninteractive
ARG JADX_VERSION
ARG GITHUB_MIRROR
ARG JADX_URL=https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl unzip; \
    mkdir -p /opt/jadx; \
    curl -fsSL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 "${GITHUB_MIRROR}${JADX_URL}" -o /tmp/jadx.zip; \
    unzip -q /tmp/jadx.zip -d /opt/jadx; \
    find /opt/jadx -type d \( \
      -name '.github' -o \
      -name 'docs' -o \
      -name 'samples' \
    \) -prune -exec rm -rf '{}' +; \
    find /opt/jadx -type f \( \
      -name '*.bat' -o \
      -name '*.md' -o \
      -name '*.map' \
    \) -delete; \
    chmod 755 /opt/jadx/bin/jadx; \
    rm -rf /tmp/* /var/tmp/* /var/lib/apt/lists/* /var/cache/apt/*

# ---------- 技能校验（build-only，不进入最终镜像） ----------
FROM debian:trixie-slim AS skills-validator

WORKDIR /tmp

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* /var/tmp/*

COPY .agents .agents
# 归一化行尾：构建上下文可能来自 Windows 检出（CRLF），而 validate-skills.sh 用
# `sed -n 1p` 与 `---` 严格比较首行 —— 带 \r 会误报「缺少 front matter」并使构建中断。
RUN set -eux; \
    find .agents -type f \( -name '*.md' -o -name '*.sh' \) -exec sed -i 's/\r$//' '{}' +; \
    find .agents/skills -mindepth 2 -name '*.sh' -type f -exec chmod 755 '{}' +; \
    chmod 755 .agents/validate-skills.sh; \
    .agents/validate-skills.sh .agents/skills

# ---------- 最终镜像：叠加在 strix 上游镜像之上 ----------
FROM ${STRIX_SANDBOX_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG OBSERVER_WARD_VERSION
ARG GITHUB_MIRROR
# Kali apt 镜像源：上游镜像自带 mirrors.neusoft.edu.cn，但它在本环境的 DNS 下只解析出
# IPv6，容器没有 IPv6 通路时 apt 会以 "Something wicked happened resolving" 失败。
ARG KALI_MIRROR=https://mirrors.aliyun.com/kali

USER root

# 上游镜像已自带：python3 / node / npm / uv / chromium / git / gcc / rg / jq / dig /
# whois / file / unzip / sudo / nmap / sqlmap / nuclei / ffuf / katana / httpx / semgrep /
# trivy / caido-cli。这里只补它**没有**的那部分。
RUN set -eux; \
    printf '%s\n' "deb ${KALI_MIRROR} kali-rolling main contrib non-free non-free-firmware" > /etc/apt/sources.list; \
    rm -f /etc/apt/sources.list.d/kali.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      apktool \
      binwalk \
      7zip \
      make \
      sqlite3 \
      openjdk-21-jdk-headless \
      xvfb \
      x11vnc \
      novnc \
      websockify \
      tor \
      supervisor \
      procps \
      ca-certificates \
      curl \
      unzip; \
    observer_ward_deb="/tmp/observer-ward.deb"; \
    curl -fsSL --retry 6 --retry-all-errors --retry-delay 3 --connect-timeout 20 "${GITHUB_MIRROR}https://github.com/emo-crab/observer_ward/releases/download/v${OBSERVER_WARD_VERSION}/observer-ward_v${OBSERVER_WARD_VERSION}_x86_64-unknown-linux-musl.deb" -o "$observer_ward_deb"; \
    apt-get install -y --no-install-recommends "$observer_ward_deb"; \
    rm -f "$observer_ward_deb"; \
    observer_ward -u; \
    ln -sf vnc.html /usr/share/novnc/index.html; \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/* /tmp/* /var/tmp/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    GHIDRA_HOME=/opt/ghidra \
    JADX_HOME=/opt/jadx \
    DISPLAY=:0 \
    PATH=/opt/jadx/bin:/opt/ghidra:/opt/ghidra/support:$PATH

COPY --from=uv-bin /uv /usr/local/bin/uv
COPY --from=uv-bin /uvx /usr/local/bin/uvx
COPY --from=agent-browser-builder /opt/agent-browser /opt/agent-browser
COPY --from=ghidra-builder /opt/ghidra /opt/ghidra
COPY --from=jadx-builder /opt/jadx /opt/jadx
COPY --from=proxy-builder --chmod=755 /sandbox-proxy /usr/local/bin/sandbox-proxy
# 平台 load_skill 以 workdir（/workspace）为基准按相对路径 .agents/skills/<name> 解析，
# 因此技能资源必须落在 /workspace/.agents/skills。
COPY --from=skills-validator /tmp/.agents/skills /workspace/.agents/skills
COPY --chmod=755 entrypoint.sh /ravenholt-entrypoint.sh
COPY supervisord.conf /etc/ravenholt/supervisord.conf

RUN set -eux; \
    ln -sf /opt/ghidra/ghidraRun /usr/local/bin/ghidra; \
    ln -sf /opt/ghidra/support/analyzeHeadless /usr/local/bin/analyzeHeadless; \
    ln -sf /opt/jadx/bin/jadx /usr/local/bin/jadx; \
    ln -sf /opt/agent-browser/bin/agent-browser-cli /usr/local/bin/agent-browser-cli; \
    mkdir -p /data; \
    chown -R pentester:pentester /workspace/.agents /data; \
    chmod -R a+rX /workspace/.agents; \
    java -version; \
    ghidra --help >/dev/null 2>&1 || true; \
    analyzeHeadless 2>&1 | head -1 || true; \
    jadx --version; \
    apktool --version; \
    binwalk --help >/dev/null; \
    observer_ward --help >/dev/null; \
    agent-browser-cli --help >/dev/null; \
    command -v supervisord; \
    command -v websockify; \
    command -v x11vnc; \
    command -v tor

# 保持上游镜像的运行身份与工作目录：strix SDK 以 pentester 身份在 /workspace 执行命令
USER pentester
WORKDIR /workspace

EXPOSE 8000

ENTRYPOINT ["/ravenholt-entrypoint.sh"]
