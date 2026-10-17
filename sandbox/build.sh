#!/bin/bash

set -eu

# GitHub Releases 在本验证环境直连会被 RST（curl 35/56），必须走加速前缀。
# 实测 gh-proxy.com 可完整下载（jadx 58MB 一次成功、ghidra 稳定传输）；
# 需要换通道时用环境变量覆盖：GITHUB_MIRROR=https://ghfast.top/ bash build.sh
GITHUB_MIRROR="${GITHUB_MIRROR:-https://gh-proxy.com/}"

echo "GitHub 加速前缀: ${GITHUB_MIRROR:-<直连>}"

docker build \
  --build-arg "GITHUB_MIRROR=${GITHUB_MIRROR}" \
  -t sandbox-runtime:latest .
