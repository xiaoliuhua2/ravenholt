#!/bin/bash
# 构建 Ravenholt 一体化沙箱镜像（sandbox-runtime:latest）
set -eu

# GitHub 加速前缀：显式指定优先；指定空串 = 直连；未指定时自动测速挑最快通道。
#   GITHUB_MIRROR=https://ghfast.top/ bash build.sh     指定通道
#   GITHUB_MIRROR= bash build.sh                        退回直连（必须用 `-` 而不是 `:-`，
#     否则空串也会被默认值覆盖，脚本里就没有「关闭加速前缀」的开关了）

# 单通道测速：取前 64 KB 读 curl 的 speed_download，输出 KB/s（不可达为 0）
probe_kbps() {
  curl -sL -m 8 -r 0-65535 -o /dev/null -w '%{speed_download}' "$1" 2>/dev/null | awk '{printf "%d", $1/1024}'
}

# 并发测速各通道并返回最快的那个前缀（日志走 stderr，只有返回值走 stdout）
pick_github_mirror() {
  local probe="https://github.com/usestrix/strix/raw/main/README.md"
  local -a names=( "直连" "gh-proxy" "ghfast" )
  local -a prefixes=( "" "https://gh-proxy.com/" "https://ghfast.top/" )
  local tmp i kbps best=-1 best_prefix="" best_name=""
  tmp="$(mktemp -d)"
  echo "  测速 GitHub 通道（并发，各取前 64 KB）..." >&2
  for i in 0 1 2; do
    ( printf '%s|%s\n' "$(probe_kbps "${prefixes[$i]}${probe}")" "${prefixes[$i]}" > "$tmp/$i" ) &
  done
  wait
  while IFS='|' read -r kbps pfx; do
    [ -n "${kbps:-}" ] || continue
    if [ "$kbps" -gt "$best" ]; then best="$kbps"; best_prefix="$pfx"; fi
  done < <(cat "$tmp"/* 2>/dev/null | sort -t'|' -k1,1 -nr)
  for i in 0 1 2; do
    [ "${prefixes[$i]}" = "$best_prefix" ] && best_name="${names[$i]}"
  done
  rm -rf "$tmp"
  if [ "$best" -le 0 ]; then
    echo "  ⚠ 所有通道都不可达 —— 退回直连（若仍失败，请检查网络后再试）" >&2
    best_prefix=""
  else
    echo "  ✓ 选用通道：${best_name}${best_prefix:+（$best_prefix）}（${best} KB/s）" >&2
  fi
  printf '%s' "$best_prefix"
}

if [ -n "${GITHUB_MIRROR+x}" ]; then
  echo "GitHub 加速前缀（显式指定）: ${GITHUB_MIRROR:-<直连>}"
else
  GITHUB_MIRROR="$(pick_github_mirror)"
  echo "GitHub 加速前缀（自动选择）: ${GITHUB_MIRROR:-<直连>}"
fi

if ! docker info >/dev/null 2>&1; then
  echo "✗ Docker 守护进程不可用 —— 先启动： systemctl enable --now docker（或 service docker start）" >&2
  exit 1
fi

BUILD_ARGS=(--build-arg "GITHUB_MIRROR=${GITHUB_MIRROR}")
# 构建阶段下载基础镜像/工具/依赖需要出网：把宿主代理透传给 build（apt 与 curl 都认）。
if [ -n "${HTTP_PROXY:-}" ]; then
  BUILD_ARGS+=(
    --build-arg "HTTP_PROXY=${HTTP_PROXY}"
    --build-arg "HTTPS_PROXY=${HTTPS_PROXY:-${HTTP_PROXY}}"
    --build-arg "NO_PROXY=${NO_PROXY:-}"
  )
fi

if docker build \
     "${BUILD_ARGS[@]}" \
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
