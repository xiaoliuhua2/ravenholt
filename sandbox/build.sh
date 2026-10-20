#!/bin/bash
# 构建 Ravenholt 一体化沙箱镜像（sandbox-runtime:latest）
set -eu

# GitHub Releases 在本验证环境直连会被 RST（curl 35/56），默认走加速前缀。
# 实测 gh-proxy.com 可完整下载（jadx 58MB 一次成功、ghidra 稳定传输）。
# 需要换通道：GITHUB_MIRROR=https://ghfast.top/ bash build.sh
# 需要退回直连：GITHUB_MIRROR= bash build.sh   （注意必须用 `-` 而不是 `:-`，
#   否则空串也会被默认值覆盖，脚本里就没有「关闭加速前缀」的开关了）
GITHUB_MIRROR="${GITHUB_MIRROR-https://gh-proxy.com/}"

echo "GitHub 加速前缀: ${GITHUB_MIRROR:-<直连>}"

if ! docker info >/dev/null 2>&1; then
  echo "✗ Docker 守护进程不可用 —— 先启动： systemctl enable --now docker（或 service docker start）" >&2
  exit 1
fi

if docker build \
     --build-arg "GITHUB_MIRROR=${GITHUB_MIRROR}" \
     -t sandbox-runtime:latest .; then
  echo "✓ 构建完成：sandbox-runtime:latest"
else
  cat >&2 <<'EOF'

✗ 镜像构建失败。最常见的原因是**拉不到基础镜像**：本镜像需要访问
  Docker Hub（debian:trixie-slim、golang:trixie）与 GHCR（usestrix/strix-sandbox、astral-sh/uv）。

处置（按顺序试）：
  ① 给 Docker 配镜像加速，然后重试 —— 编辑 /etc/docker/daemon.json：
       { "registry-mirrors": ["https://docker.m.daocloud.io"] }
     之后 systemctl restart docker
  ② 先手工验证通路（能拉下来再构建）：
       docker pull ghcr.io/usestrix/strix-sandbox:1.3.0
       docker pull debian:trixie-slim
  ③ 完全离线：在能联网的机器上构建，然后迁移镜像：
       构建机： docker save sandbox-runtime:latest -o sandbox.tar
       本  机： docker load -i sandbox.tar
EOF
  exit 1
fi
