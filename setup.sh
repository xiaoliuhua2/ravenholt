#!/usr/bin/env bash
# ============================================================
# Ravenholt 一键部署脚本
#
#   环境检测 → 系统依赖 → 配置初始化 → PostgreSQL → Python 依赖
#   → 前端构建 → 沙箱镜像(可选) → 安装后自检
#
# 适用环境：Linux x64（推荐 Kali / Debian）
# 用法：
#   bash setup.sh                 # 检测 + 安装 + 部署（缺 Node.js / Docker 会自动装）
#   bash setup.sh --check         # 仅环境检测，不改动任何文件
#   bash setup.sh --deps-only     # 只装系统依赖（Node.js / Docker 等）后退出
#   bash setup.sh --no-deps       # 跳过系统依赖与 Node.js / Docker 的自动安装
#   bash setup.sh --with-sandbox  # 额外自动构建沙箱镜像（下载量大、耗时长）
#   bash setup.sh --rebuild-frontend  # 强制重建前端产物（默认 web/dist-app 已存在时跳过）
#
# 说明：本脚本只针对 ravenholt 当前结构；幂等，已存在的配置不会被覆盖。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
WORKSPACE_DIR="$PROJECT_DIR/.ravenholt"
CONFIG_FILE="$WORKSPACE_DIR/config.json"
POLICY_FILE="$WORKSPACE_DIR/policy.yaml"
PY_MIN_MAJOR=3
PY_MIN_MINOR=12

usage() {
  cat <<'EOF'
Ravenholt 一键部署脚本

  流程：环境检测 → 系统依赖 → 配置初始化 → PostgreSQL → Python 依赖
        → 前端构建 → 沙箱镜像(可选) → 安装后自检

适用环境：Linux x64（推荐 Kali / Debian）

用法：
  bash setup.sh                 检测 + 安装 + 部署（缺 Node.js / Docker 会自动安装）
  bash setup.sh --check         仅环境检测，不改动任何文件
  bash setup.sh --deps-only     只装系统依赖（Node.js / Docker 等）后退出，便于分步执行
  bash setup.sh --no-deps       跳过系统依赖与 Node.js / Docker 的自动安装
  bash setup.sh --with-sandbox  额外自动构建沙箱镜像（下载量大、耗时长）
  bash setup.sh --rebuild-frontend  强制重建前端产物（已存在 web/dist-app 时默认跳过）
  bash setup.sh -h | --help     显示本帮助

说明：更新替代，已存在的 .ravenholt/config.json、policy.yaml 不会被覆盖。
      Node.js 走官方二进制（可设 NODE_MIRROR / NODE_VERSION 覆盖源与版本）；
      Docker 走发行版包 docker.io 并自动启动守护进程。
EOF
}

CHECK_ONLY=0
WITH_SANDBOX=0
DEPS_ONLY=0
NO_DEPS=0
REBUILD_FRONTEND=0
for arg in "$@"; do
  case "$arg" in
    --check|-c)         CHECK_ONLY=1 ;;
    --deps-only)        DEPS_ONLY=1 ;;
    --no-deps)          NO_DEPS=1 ;;
    --with-sandbox)     WITH_SANDBOX=1 ;;
    --rebuild-frontend) REBUILD_FRONTEND=1 ;;
    -h|--help)          usage; exit 0 ;;
    *) printf "未知参数: %s（可用: --check / --deps-only / --no-deps / --with-sandbox / --rebuild-frontend / --help）\n" "$arg"; exit 2 ;;
  esac
done

# ── 输出 ────────────────────────────────────────────────────
C_RED='\033[0;31m'; C_GRN='\033[0;32m'; C_YEL='\033[1;33m'; C_BLU='\033[0;34m'; C_DIM='\033[2m'; C_NC='\033[0m'
OK_N=0; WARN_N=0; FAIL_N=0
step() { printf "\n${C_BLU}══ %s${C_NC}\n" "$1"; }
ok()   { printf "  ${C_GRN}✓${C_NC} %s\n" "$1"; OK_N=$((OK_N+1)); }
warn() { printf "  ${C_YEL}!${C_NC} %s\n" "$1"; WARN_N=$((WARN_N+1)); }
bad()  { printf "  ${C_RED}✗${C_NC} %s\n" "$1"; FAIL_N=$((FAIL_N+1)); }
info() { printf "  ${C_DIM}·${C_NC} %s\n" "$1"; }
fatal(){ printf "\n${C_RED}[✗] %s${C_NC}\n" "$1" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
can_root() { [ "$(id -u)" -eq 0 ] || have sudo; }
py_ok() { python3 -c "import sys;raise SystemExit(0 if sys.version_info>=(${PY_MIN_MAJOR},${PY_MIN_MINOR}) else 1)" 2>/dev/null; }

# 以 postgres 超级用户身份执行 psql（参数与 psql 相同）。
# root 下走 su（-s 绕过 postgres 用户的 nologin shell）；非 root 走免密 sudo（-n，避免交互阻塞）。
psql_super() {
  # 优先用 sudo 以**参数数组**形式透传：SQL 里带引号的字面量（如 PASSWORD 'xxx'）
  # 若经 `printf '%q'` 生成字符串再交给 sh 解析，单引号会被吞掉导致语法错误
  # （CREATE USER/ALTER USER 一律失败，进而建库失败、平台起不来）。
  if have sudo; then
    sudo -n -u postgres psql "$@"
  elif [ "$(id -u)" -eq 0 ]; then
    # 无 sudo 时的回退：改用 bash 解析 %q 转义（dash 会丢引号）
    su -s /bin/bash -c "$(printf '%q ' psql "$@")" postgres
  else
    return 127
  fi
}

# 把平台沙箱镜像名写入 .ravenholt/config.json 的 sandbox.image（**仅当该项为空**）。
# 目的：让「构建了镜像 → 会话就用它」这条链路零手工；已有值一律保留，不覆盖部署者选择。
pin_sandbox_image() {
  local image="$1"
  [ -f "$CONFIG_FILE" ] || return 0
  python3 - "$CONFIG_FILE" "$image" 2>/dev/null <<'PYEOF' || true
import json, sys

path, image = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    raise SystemExit(0)

sandbox = cfg.setdefault("sandbox", {})
current = str(sandbox.get("image", "") or "").strip()
if current:
    print(f"  · 保留现有 sandbox.image = {current}")
else:
    sandbox["image"] = image
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    print(f"  ✓ 已写入 sandbox.image = {image}（之后启动的会话将使用该镜像）")
PYEOF
}


# 读取 .ravenholt/config.json 的点分路径值（如 system.bootstrap_admin.email），缺失返回空串。
cfg_get() {
  python3 - "$CONFIG_FILE" "$1" 2>/dev/null <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    raise SystemExit(0)
node = cfg
for key in sys.argv[2].split("."):
    node = node.get(key) if isinstance(node, dict) else None
    if node is None:
        break
print("" if node is None else node)
PYEOF
}

# 下载：进度交给 curl 自带的进度条（速率 / 已下载 / 剩余时间），不再自写 \r 循环。
# 两点讲究：
#   · 不接任何管道 —— 管道会缓冲输出，下载期间屏幕上什么都没有（apt 曾因此"看着卡死"）；
#   · curl 的进度与错误直接进终端，失败时能一眼看到原因（如 404 / 连接被拒）。
fetch_with_progress() {
  local url="$1" out="$2" label="${3:-下载}"
  local size
  info "$label：开始下载（下方进度条实时显示速率与剩余时间）..."
  if curl -fL --progress-bar --retry 2 --retry-all-errors --retry-delay 3 \
       --connect-timeout 20 --max-time 900 "$url" -o "$out"; then
    size="$(awk -v b="$(stat -c %s "$out" 2>/dev/null || echo 0)" 'BEGIN{printf "%.2f", b/1048576}')"
    ok "$label：下载完成（${size} MB）"
    return 0
  fi
  warn "$label：下载失败 —— 换源后重跑，或用 NODE_MIRROR 指定可达镜像"
  return 1
}

# 前台静默任务（npm install / npm run build）加心跳：完整日志落文件，屏幕每 3 秒刷新"进行中 N 秒"。
# 目的同 fetch_with_progress：长任务静默会让人误判卡死。
run_with_heartbeat() {
  local label="$1" logfile="$2"; shift 2
  local pid t0 elapsed
  t0="$(date +%s)"
  "$@" > "$logfile" 2>&1 &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  %s 进行中… %s 秒      " "$label" "$(( $(date +%s) - t0 ))"
    sleep 1
  done
  wait "$pid"; local rc=$?
  elapsed=$(( $(date +%s) - t0 ))
  if [ "$rc" -eq 0 ]; then
    printf "\r  %s 完成（用时 %s 秒）%*s\n" "$label" "$elapsed" 16 ""
  else
    printf "\r%*s\r" 60 ""
  fi
  return "$rc"
}

# Node.js 是否满足前端构建的最低要求（Vite 8 需 >= 20.19）
node_ver_ok() {
  have node || return 1
  node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit((a>20)||(a===20&&b>=19)?0:1)' 2>/dev/null
}

# 安装 Node.js：下载官方二进制解压到 /usr/local。
# 不依赖发行版仓库版本（Debian 12 的 nodejs 只有 18），也不引入 nodesource 第三方源。
# 官方源不可达时自动回退清华镜像；可用 NODE_MIRROR / NODE_VERSION 覆盖。
install_node() {
  local node_version="${NODE_VERSION:-v22.11.0}"
  local node_mirror="${NODE_MIRROR:-https://nodejs.org/dist}"
  local fallback_mirror="https://mirrors.tuna.tsinghua.edu.cn/nodejs-release/"
  local narch
  case "$(uname -m)" in
    x86_64|amd64)  narch=linux-x64 ;;
    aarch64|arm64) narch=linux-arm64 ;;
    *) warn "架构 $(uname -m) 无官方 Node 二进制，请手动安装 Node.js >= 20.19"; return 1 ;;
  esac

  if ! can_root; then
    warn "无 root/sudo，无法自动安装 Node.js —— 请手动安装 >= 20.19 后重跑本脚本"
    info "参考：${node_mirror}/${node_version}/node-${node_version}-${narch}.tar.xz"
    return 1
  fi

  local tarball="node-${node_version}-${narch}.tar.xz"
  local tmp; tmp="$(mktemp -d)" || return 1
  local src="${node_mirror}/${node_version}/${tarball}"

  if ! fetch_with_progress "$src" "$tmp/$tarball" "Node.js ${node_version}"; then
    info "官方源不可达，改用镜像源"
    src="${fallback_mirror}${node_version}/${tarball}"
    if ! fetch_with_progress "$src" "$tmp/$tarball" "Node.js ${node_version}（镜像源）"; then
      rm -rf "$tmp"
      warn "Node.js 下载失败（网络受限？）—— 可设置 NODE_MIRROR=<可用镜像> 后重跑"
      return 1
    fi
  fi

  if ! tar -xJf "$tmp/$tarball" -C "$tmp" >/dev/null 2>&1; then
    rm -rf "$tmp"
    warn "Node.js 解压失败 —— 缺少 xz 支持？可先 apt install -y xz-utils 后重跑"
    return 1
  fi

  # 官方包结构固定为 node-<ver>-<arch>/{bin,lib,include,share}；cp -a 保留 bin/npm 等符号链接
  if [ "$(id -u)" -eq 0 ]; then
    cp -a "$tmp/node-${node_version}-${narch}/." /usr/local/
  else
    sudo cp -a "$tmp/node-${node_version}-${narch}/." /usr/local/
  fi
  rm -rf "$tmp"
  hash -r
  return 0
}

# 安装并启动 Docker（Kali / Debian 的包名均为 docker.io）。
# 守护进程启动失败只告警不中断：平台与渗透会话在无 Docker 时仍可运行（沙箱功能受限）。
install_docker() {
  if ! can_root; then
    warn "无 root/sudo，无法自动安装 Docker —— 请手动安装后重跑本脚本"
    info "参考：sudo apt install -y docker.io && sudo systemctl enable --now docker"
    return 1
  fi
  local APT
  if [ "$(id -u)" -eq 0 ]; then
    APT=(env DEBIAN_FRONTEND=noninteractive apt-get)
  else
    APT=(sudo env DEBIAN_FRONTEND=noninteractive apt-get)
  fi

  info "apt 安装 docker.io（含 containerd/runc/iptables 等依赖，视网络需下载数十至百余 MB）..."
  info "apt 的 Get/Setting up 行即为进展；若长时间没有新行，请看提示：换 Kali 镜像源，或等其它 apt 进程释放锁"
  if ! "${APT[@]}" install -y docker.io; then
    warn "Docker 安装未完成 —— 请手动执行：sudo apt install -y docker.io（或换镜像源后重试）"
    return 1
  fi
  # compose：v2 插件包与 v1 独立包在不同发行版上包名不同，两者都试一次
  if ! have docker-compose; then
    "${APT[@]}" install -y docker-compose-v2 >/dev/null 2>&1 \
      || "${APT[@]}" install -y docker-compose >/dev/null 2>&1 || true
  fi
  # 启动守护进程；无 systemd 的环境（容器内）回退到 service
  systemctl enable --now docker >/dev/null 2>&1 || service docker start >/dev/null 2>&1 || true
  sleep 3
  docker info >/dev/null 2>&1
}

printf "========================================\n"
printf "  Ravenholt 一键部署\n"
printf "========================================\n"

# ============================================================
# 1. 环境检测
# ============================================================
step "1/8 环境检测"

# 1.1 操作系统
OS_NAME="$(uname -s)"
if [ "$OS_NAME" = "Linux" ]; then
  DISTRO="$( (grep -h '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"') || echo unknown )"
  ok "系统: Linux（$DISTRO）"
else
  bad "系统: $OS_NAME —— 本脚本仅支持 Linux（推荐 Kali/Debian）"
fi

# 1.2 架构（沙箱镜像仅支持 x64）
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ok "架构: $ARCH" ;;
  *) warn "架构: $ARCH —— 沙箱镜像仅支持 x64/amd64，本机无法构建/运行渗透沙箱" ;;
esac

# 1.3 Python（>= 3.12）
if have python3; then
  PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo '未知')"
  if py_ok; then ok "Python: $PYV"; else bad "Python: $PYV —— 需要 >= ${PY_MIN_MAJOR}.${PY_MIN_MINOR}（推荐 3.13），待第 2 段尝试安装/需你手动升级）"; fi
  python3 -c 'import venv' 2>/dev/null && ok "venv 模块可用" || bad "缺少 venv 模块（第 2 段将尝试 apt install python3-venv）"
else
  bad "Python3 未安装（第 2 段将尝试 apt install python3）"
fi

# 1.4 Node（Vite 8 要求 >= 20.19）
if have node; then
  NODEV="$(node -v 2>/dev/null)"
  if node_ver_ok; then
    ok "Node.js: $NODEV"
  else
    warn "Node.js: $NODEV —— 前端构建需要 >= 20.19，第 2 段将自动升级到 22（官方二进制）"
  fi
  have npm && ok "npm: $(npm -v 2>/dev/null)" || warn "npm 未找到（随 Node.js 一起安装，第 2 段会补齐）"
else
  warn "Node.js 未安装 —— 第 2 段将自动安装（官方二进制 22.x，满足前端构建要求）"
fi

# 1.5 Docker（渗透沙箱运行时；缺失则功能受限）
if have docker; then
  ok "Docker: $(docker --version 2>/dev/null | sed 's/^Docker version //;s/,.*//')"
  if docker compose version >/dev/null 2>&1 || have docker-compose; then
    ok "Docker Compose 可用"
  else
    warn "Docker Compose 未找到（docker-compose.prod.yml 需要）—— 第 2 段将尝试安装"
  fi
  docker info >/dev/null 2>&1 || warn "Docker 守护进程未运行 —— 第 2 段将尝试启动"
else
  warn "Docker 未安装 —— 第 2 段将自动安装 docker.io 并启动守护进程"
fi

# 1.6 PostgreSQL
if have psql; then
  ok "PostgreSQL 客户端: $(psql --version 2>/dev/null | awk '{print $3}')"
else
  warn "psql 未安装（第 2 段将尝试 apt install postgresql postgresql-client）"
fi
have pg_isready && { pg_isready -q 2>/dev/null && ok "PostgreSQL 服务已在运行" || info "PostgreSQL 服务未运行（稍后会自动启动）"; }

# 1.7 权限
if [ "$(id -u)" -eq 0 ]; then ok "权限: root"
elif have sudo; then ok "权限: 可用 sudo"
else warn "权限: 非 root 且无 sudo，系统依赖/数据库可能无法自动配置"; fi

# 1.8 端口 8000
if ! have ss; then
  info "未检测端口占用（缺少 ss 命令）"
elif ss -ltn 2>/dev/null | grep -qE ':8000[[:space:]]'; then
  warn "端口 8000 已被占用 —— 安装完成后启动前请先释放（bash serve.sh stop）"
else
  ok "端口 8000 空闲"
fi

# 1.9 磁盘
AVAIL_KB="$(df -Pk "$PROJECT_DIR" 2>/dev/null | awk 'NR==2{print $4}')"
if [ -n "${AVAIL_KB:-}" ]; then
  AVAIL_MB=$((AVAIL_KB/1024))
  [ "$AVAIL_MB" -ge 2048 ] && ok "磁盘可用: ${AVAIL_MB} MB" || warn "磁盘可用: ${AVAIL_MB} MB —— 依赖与镜像建议 >= 2 GB（沙箱镜像另需 3+ GB）"
fi

printf "  ${C_DIM}检测汇总：ok=%d  warn=%d  fail=%d${C_NC}\n" "$OK_N" "$WARN_N" "$FAIL_N"

if [ "$CHECK_ONLY" -eq 1 ]; then
  printf "\n仅检测模式（--check），未做任何改动。\n"
  exit 0
fi

if [ "$OS_NAME" != "Linux" ]; then
  fatal "本脚本仅支持 Linux（推荐 Kali/Debian）。当前系统：$OS_NAME"
fi

# ============================================================
# 2. 系统依赖（安装 + 硬性依赖复检）
# ============================================================
step "2/8 安装系统依赖"
PKGS=""
have psql || PKGS="$PKGS postgresql postgresql-client"
have python3 || PKGS="$PKGS python3"
if have python3; then
  python3 -c 'import venv' 2>/dev/null || PKGS="$PKGS python3-venv"
  python3 -c 'import pip' 2>/dev/null || PKGS="$PKGS python3-pip"
fi
have curl    || PKGS="$PKGS curl"
have openssl || PKGS="$PKGS openssl"

if [ -n "${PKGS// /}" ]; then
  if ! can_root; then
    warn "无 root/sudo，跳过系统依赖安装。请手动执行：sudo apt install -y $PKGS"
  else
    info "apt 安装：$PKGS"
    if [ "$(id -u)" -eq 0 ]; then
      APT=(env DEBIAN_FRONTEND=noninteractive apt-get)
    else
      APT=(sudo env DEBIAN_FRONTEND=noninteractive apt-get)
    fi
    # 不把 apt 输出接进管道：管道会缓冲全部输出，下载期间屏幕上看不到任何进展
    if "${APT[@]}" update -qq && "${APT[@]}" install -y $PKGS; then
      ok "系统依赖已安装"
    else
      warn "apt 安装未完成，请手动执行：sudo apt install -y $PKGS"
    fi
  fi
else
  ok "系统依赖已就绪"
fi

# ---- Node.js（前端构建；缺失或版本过低则自动安装）----
if [ "$NO_DEPS" -eq 1 ]; then
  info "已指定 --no-deps，跳过 Node.js 自动安装"
elif node_ver_ok; then
  ok "Node.js 已就绪：$(node -v)（npm $(npm -v 2>/dev/null || echo '?')）"
elif install_node && node_ver_ok; then
  hash -r
  ok "Node.js 已安装：$(node -v)（npm $(npm -v 2>/dev/null || echo '?')）"
else
  warn "Node.js 不可用 —— 第 6 段将跳过前端构建（后端与平台仍可运行）"
fi

# ---- Docker（渗透/审计沙箱运行时；缺失则自动安装并启动）----
if [ "$NO_DEPS" -eq 1 ]; then
  info "已指定 --no-deps，跳过 Docker 自动安装"
elif have docker && docker info >/dev/null 2>&1; then
  ok "Docker 已就绪"
elif have docker; then
  info "Docker 已安装但守护进程未运行 —— 尝试启动"
  if [ "$(id -u)" -eq 0 ]; then
    systemctl enable --now docker >/dev/null 2>&1 || service docker start >/dev/null 2>&1 || true
  else
    sudo systemctl enable --now docker >/dev/null 2>&1 || sudo service docker start >/dev/null 2>&1 || true
  fi
  sleep 3
  if docker info >/dev/null 2>&1; then ok "Docker 守护进程已启动"; else warn "Docker 守护进程未能启动 —— 沙箱功能不可用"; fi
elif install_docker; then
  ok "Docker 已安装并启动：$(docker --version 2>/dev/null | sed 's/^Docker version //;s/,.*//')"
else
  warn "Docker 未就绪 —— 渗透沙箱不可用；平台仍可启动（稍后装好 Docker 再重跑本脚本即可）"
fi

# ---- 硬性依赖复检（安装之后再判定，避免"缺 Python 直接退出、装都不装"）----
HARD_MISS=0
if ! have python3; then
  bad "Python3 仍不可用 —— 请手动安装（apt install python3 python3-venv python3-pip）"; HARD_MISS=1
else
  if py_ok; then
    ok "Python: $(python3 -V 2>&1 | awk '{print $2}')"
  else
    bad "Python 版本仍 < ${PY_MIN_MAJOR}.${PY_MIN_MINOR} —— 请升级后重跑本脚本"; HARD_MISS=1
  fi
  python3 -c 'import venv' 2>/dev/null || { bad "venv 模块仍不可用（apt install python3-venv）"; HARD_MISS=1; }
fi
if [ "$HARD_MISS" -ne 0 ]; then
  fatal "硬性依赖未满足，请按上面的提示处理后重跑：bash setup.sh"
fi

# 分步执行出口：只装环境，后续构建/部署由用户自行决定时机
if [ "$DEPS_ONLY" -eq 1 ]; then
  printf "\n${C_BLU}══ 系统依赖安装完成（--deps-only）${C_NC}\n"
  printf "  Node.js: %s | Docker: %s\n" \
    "$(node -v 2>/dev/null || echo '不可用')" \
    "$(have docker && docker info >/dev/null 2>&1 && echo '可用' || echo '不可用')"
  printf "  后续可分别执行：\n"
  printf "    · 完整部署（配置 / 数据库 / 依赖 / 前端）： bash setup.sh\n"
  printf "    · 仅构建前端： cd web && npm install && npm run build\n"
  printf "    · 仅构建沙箱镜像： cd sandbox && bash build.sh\n"
  printf "    · 启动平台： bash serve.sh start\n"
  exit 0
fi

# ============================================================
# 3. 配置初始化
# ============================================================
step "3/8 初始化配置"
mkdir -p "$WORKSPACE_DIR"

if [ -f "$CONFIG_FILE" ]; then
  ok "config.json 已存在，保留不覆盖"
  ADMIN_EMAIL="$(cfg_get system.bootstrap_admin.email)"
  info "管理员邮箱：${ADMIN_EMAIL:-（见 .ravenholt/config.json）}"
  info "（如忘记管理员口令，可删除该文件后重跑本脚本重新生成）"
else
  [ -f "$WORKSPACE_DIR/config.json.example" ] || fatal "缺少 .ravenholt/config.json.example"
  cp "$WORKSPACE_DIR/config.json.example" "$CONFIG_FILE"

  # 生成随机密钥与强口令（仅此一次输出到终端）
  GEN_OUT="$(python3 - "$CONFIG_FILE" <<'PYEOF'
import json, secrets, sys
path = sys.argv[1]
cfg = json.load(open(path, encoding="utf-8"))
encrypt_key = secrets.token_urlsafe(48)
db_pwd      = secrets.token_urlsafe(18)
admin_pwd   = secrets.token_urlsafe(12)
cfg.setdefault("system", {})["encrypt_key"] = encrypt_key
adm = cfg["system"].setdefault("bootstrap_admin", {})
adm["enabled"]  = True
adm["password"] = admin_pwd
db = cfg.setdefault("database", {})
db["host"]     = "127.0.0.1"
db["port"]     = 5432
db["database"] = db.get("database") or "ravenholt"
db["username"] = db.get("username") or "root"
db["password"] = db_pwd
for agent in (cfg.get("agents") or {}).values():
    agent["api_key"] = ""
json.dump(cfg, open(path, "w", encoding="utf-8"), indent=4, ensure_ascii=False)
print(adm.get("email", ""))
print(admin_pwd)
print(db["database"])
print(db["username"])
print(db_pwd)
PYEOF
)"
  ADMIN_EMAIL="$(printf '%s' "$GEN_OUT" | sed -n '1p')"
  ADMIN_PWD="$(printf '%s' "$GEN_OUT" | sed -n '2p')"
  DB_NAME="$(printf '%s' "$GEN_OUT" | sed -n '3p')"
  DB_USER="$(printf '%s' "$GEN_OUT" | sed -n '4p')"
  DB_PWD="$(printf '%s' "$GEN_OUT" | sed -n '5p')"
  ok "config.json 已生成（encrypt_key / 数据库口令 / 管理员口令均为随机生成）"
fi

# 红线策略：fail-closed —— 文件缺失平台会拒绝启动，必须存在
if [ -f "$POLICY_FILE" ]; then
  ok "policy.yaml 已存在，保留不覆盖"
elif [ -f "$WORKSPACE_DIR/policy.yaml.example" ]; then
  cp "$WORKSPACE_DIR/policy.yaml.example" "$POLICY_FILE"
  ok "policy.yaml 已从示例生成（平台对它是 fail-closed，缺失将拒绝启动）"
else
  warn "缺少 .ravenholt/policy.yaml.example，无法生成 policy.yaml —— 平台将因 fail-closed 拒绝启动"
fi

# 技能路由：可选，缺失时回退工厂默认（core/strix_runtime/skill_routes.default.yaml）
if [ -f "$WORKSPACE_DIR/skill_routes.yaml" ]; then
  ok "skill_routes.yaml 已存在，保留不覆盖"
else
  info "skill_routes.yaml 未生成（可选）—— 缺失时使用工厂默认技能路由表"
  info "如需自定义：cp .ravenholt/skill_routes.yaml.example .ravenholt/skill_routes.yaml 后自行编辑"
fi

# ============================================================
# 4. PostgreSQL（建库建角色，仅本机库）
# ============================================================
step "4/8 配置 PostgreSQL"
DB_HOST="$(cfg_get database.host)"; DB_HOST="${DB_HOST:-127.0.0.1}"
DB_NAME="$(cfg_get database.database)"; DB_NAME="${DB_NAME:-ravenholt}"
DB_USER="$(cfg_get database.username)"; DB_USER="${DB_USER:-root}"
DB_PWD="$(cfg_get database.password)"

if [ -z "$DB_PWD" ]; then
  warn "config.json 未读取到数据库口令，跳过建库（请手工创建库 $DB_NAME 并保证 config.json 正确）"
elif ! have psql; then
  warn "psql 不可用，跳过数据库初始化（请自行准备 PostgreSQL）"
elif [ "$DB_HOST" != "127.0.0.1" ] && [ "$DB_HOST" != "localhost" ]; then
  warn "config.json 指向远端数据库 $DB_HOST，跳过本机建库（请自行在远端创建库 $DB_NAME）"
else
  # 启动服务
  if have pg_isready && pg_isready -q 2>/dev/null; then
    ok "PostgreSQL 已在运行"
  else
    info "启动 PostgreSQL..."
    if can_root; then
      if [ "$(id -u)" -eq 0 ]; then ROOT_RUN=(); else ROOT_RUN=(sudo); fi
      "${ROOT_RUN[@]}" systemctl start postgresql 2>/dev/null \
        || "${ROOT_RUN[@]}" pg_ctlcluster "$(ls /etc/postgresql 2>/dev/null | sort -n | tail -1)" main start 2>/dev/null \
        || "${ROOT_RUN[@]}" service postgresql start 2>/dev/null
      sleep 2
    fi
    if have pg_isready && pg_isready -q 2>/dev/null; then ok "PostgreSQL 已启动"; else warn "无法启动 PostgreSQL，请手动启动后重跑本脚本"; fi
  fi

  # 先做一次连通性自检：把失败原因原样露出来（不再被 >/dev/null 吞掉）
  if PGCONN_OUT="$(psql_super -tAc 'SELECT 1;' 2>&1)"; then
    ok "已以 postgres 超级用户连上数据库"
    PG_READY=1
  else
    PG_READY=0
    warn "无法以 postgres 超级用户连接数据库：${PGCONN_OUT:-（无输出，返回码 $?）}"
    warn "请确认当前用户能 su/sudo 到 postgres；或手动建库后重跑本脚本"
  fi

  if [ "$PG_READY" -eq 1 ]; then
    # 角色：不存在则建，存在则把口令对齐到 config.json（保证二者一致）
    if psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null | grep -q 1; then
      info "角色 $DB_USER 已存在 —— 将其口令对齐为 config.json 中的值（若该角色还服务于其它应用，请注意）"
      if SQL_OUT="$(psql_super -c "ALTER USER \"$DB_USER\" WITH PASSWORD '$DB_PWD';" 2>&1)"; then
        ok "角色 $DB_USER 口令已对齐"
      else
        warn "设置角色 $DB_USER 口令失败：$SQL_OUT"
      fi
    else
      if SQL_OUT="$(psql_super -c "CREATE USER \"$DB_USER\" WITH PASSWORD '$DB_PWD';" 2>&1)"; then
        ok "角色 $DB_USER 已创建"
      else
        warn "创建角色 $DB_USER 失败：$SQL_OUT"
      fi
    fi
    # 数据库
    if psql_super -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
      ok "数据库 $DB_NAME 已存在"
    else
      if SQL_OUT="$(psql_super -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" 2>&1)"; then
        ok "数据库 $DB_NAME 已创建"
      else
        warn "创建数据库 $DB_NAME 失败：$SQL_OUT"
      fi
    fi
  fi
fi

# ============================================================
# 5. Python 依赖
# ============================================================
step "5/8 安装 Python 依赖"
[ -f "$PROJECT_DIR/requirements.txt" ] || fatal "缺少 requirements.txt"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR" && ok "虚拟环境已创建：.venv" || fatal "创建虚拟环境失败"
else
  ok "虚拟环境已存在：.venv"
fi
PY="$VENV_DIR/bin/python"
# 输出精简：pip 会把每个已满足的依赖都打印一行 "Requirement already satisfied: ..."（几十行、
# 没有信息量），因此成功路径改为 -q 静默 + 心跳，只有失败时才把完整日志打印出来。
info "pip 安装依赖（阿里云镜像；成功只打印一行，失败会打印完整日志）..."
"$PY" -m pip install -q --no-input -i https://mirrors.aliyun.com/pypi/simple/ --upgrade pip || true
PIP_LOG="$PROJECT_DIR/.pip-install.log"
if run_with_heartbeat "pip install" "$PIP_LOG" \
     "$PY" -m pip install -q --no-input -i https://mirrors.aliyun.com/pypi/simple/ -r "$PROJECT_DIR/requirements.txt"; then
  rm -f "$PIP_LOG"
  ok "Python 依赖已安装（requirements.txt）"
else
  warn "Python 依赖安装失败，完整输出如下："
  cat "$PIP_LOG"
  fatal "Python 依赖安装失败，请检查网络/镜像后重跑本脚本"
fi

# ============================================================
# 6. 前端构建
# ============================================================
step "6/8 构建前端"
hash -r   # 第 2 段可能刚装好 Node.js，清掉 shell 的命令路径缓存
if [ -d "$PROJECT_DIR/web" ]; then
  if ! have node; then
    warn "未安装 Node.js，跳过前端构建（后端仍可跑，但界面缺失）"
  elif [ -f "$PROJECT_DIR/web/dist-app/index.html" ] && [ "$REBUILD_FRONTEND" -eq 0 ]; then
    # 前端产物已就绪就跳过整段构建：省下每次重跑 npm install / npm run build 的时间
    ok "前端产物已存在：web/dist-app（跳过构建；需要重建请加 --rebuild-frontend）"
  else
    cd "$PROJECT_DIR/web"
    # web/openapi.json 已随仓库提交；缺失时回退根 openapi.json
    if [ ! -f "$PROJECT_DIR/web/openapi.json" ] && [ -f "$PROJECT_DIR/openapi.json" ]; then
      ln -sf "$PROJECT_DIR/openapi.json" "$PROJECT_DIR/web/openapi.json"
      info "已链接 web/openapi.json -> openapi.json"
    fi
    if [ ! -d node_modules/openapi-typescript ] || [ ! -d node_modules/vite ]; then
      NPM_LOG="$PROJECT_DIR/web/.npm-install.log"
      info "npm install（数百个包，心跳表示仍在进行；完整日志写入 .npm-install.log）..."
      # 主安装就带上 --include=optional：npm 在空白环境会**静默跳过** optionalDependencies，
      # 而 Vite 8 的 rolldown 依赖平台原生绑定（@rolldown/binding-<plat>），缺了必然构建失败。
      if run_with_heartbeat "npm install" "$NPM_LOG" npm install --include=optional; then
        ok "前端依赖已安装"
      else
        tail -20 "$NPM_LOG"; warn "npm install 失败，跳过前端构建"
      fi
      rm -f "$NPM_LOG"
    else
      ok "前端依赖已就绪"
    fi
    if [ -d node_modules/vite ]; then
      BUILD_LOG="$PROJECT_DIR/web/.build.log"
      FIX_LOG="$PROJECT_DIR/web/.npm-fix.log"
      info "npm run build（generate:api → tsc → vite build；心跳表示仍在进行）..."
      BUILD_OK=0
      BIND_PLAT=""
      if run_with_heartbeat "npm run build" "$BUILD_LOG" npm run build; then
        BUILD_OK=1
        tail -2 "$BUILD_LOG"; ok "前端构建完成：web/dist-app"
      elif grep -qE "MODULE_NOT_FOUND|Cannot find module" "$BUILD_LOG"; then
        # 自愈第 ① 步：npm install --include=optional。
        # 实测（Kali + rolldown 1.0.2）：这一步**往往补不回** —— package-lock 里该 optional
        # 条目已存在，npm 认为无需处理，于是依旧缺 .node；真正生效的是第 ② 步。
        info "构建失败疑似缺少可选依赖（原生绑定），补装后重试..."
        run_with_heartbeat "npm install --include=optional" "$FIX_LOG" npm install --include=optional || true
        if run_with_heartbeat "npm run build（重试）" "$BUILD_LOG" npm run build; then
          BUILD_OK=1
          tail -2 "$BUILD_LOG"; ok "前端构建完成（补装可选依赖后重试成功）：web/dist-app"
        else
          # 自愈第 ② 步：从报错里解析缺失的绑定名，按 rolldown 的实际版本显式安装该平台包。
          # 显式安装会把下载/报错原样打印出来；不像 npm 对 optional 依赖那样一声不吭地跳过。
          BIND_PLAT="$(sed -n 's/.*rolldown-binding\.\([A-Za-z0-9_-]*\)\.node.*/\1/p' "$BUILD_LOG" | head -n 1)"
          RD_VER="$(node -p "try{require('rolldown/package.json').version}catch(e){''}" 2>/dev/null)"
          if [ -n "$BIND_PLAT" ] && [ -n "$RD_VER" ]; then
            info "缺少 $BIND_PLAT 原生绑定，按 rolldown $RD_VER 显式安装 @rolldown/binding-$BIND_PLAT ..."
            if run_with_heartbeat "npm install @rolldown/binding-$BIND_PLAT@$RD_VER" "$FIX_LOG" \
                 npm install --no-save --prefer-offline "@rolldown/binding-$BIND_PLAT@$RD_VER"; then
              info "绑定包安装结果：$(tail -n 1 "$FIX_LOG")"
              if run_with_heartbeat "npm run build（补装绑定后重试）" "$BUILD_LOG" npm run build; then
                BUILD_OK=1
                tail -2 "$BUILD_LOG"; ok "前端构建完成（显式安装原生绑定后成功）：web/dist-app"
              fi
            else
              printf "\r%*s\r" 60 ""
              tail -15 "$FIX_LOG"
            fi
          else
            warn "未能从日志解析缺失绑定名（或 rolldown 未安装），跳过显式补装"
          fi
        fi
      fi
      if [ "$BUILD_OK" -eq 0 ]; then
        tail -25 "$BUILD_LOG"
        warn "前端构建失败，请检查上方日志"
        info "处置：① 换 npm 源后重跑： npm config set registry https://registry.npmmirror.com"
        info "      ② 手工补装绑定： cd web && npm install @rolldown/binding-${BIND_PLAT:-linux-x64-gnu} 再 npm run build"
      fi
      rm -f "$BUILD_LOG" "$FIX_LOG"
    fi
    cd "$PROJECT_DIR"
  fi
else
  warn "无 web 目录，跳过前端构建"
fi

# ============================================================
# 7. 沙箱镜像（可选）
# ============================================================
step "7/8 沙箱镜像"
# sandbox/build.sh 产出的是**一体化镜像** sandbox-runtime:latest：以上游 strix-sandbox
# 镜像为基础，叠加 Ravenholt 的定制能力（Ghidra / Jadx / apktool / binwalk /
# observer_ward / agent-browser-cli + 容器内 Go 控制面 + .agents/skills 技能资源）。
# 因此它同时满足两种用途：
#   A) strix 会话沙箱 —— agent 在渗透/审计会话里执行命令的容器（含 Caido 抓包）
#   B) 平台「沙箱容器」的人工控制台 —— 终端 / 文件管理 / noVNC / egress 动态刷新
# 不构建也不影响渗透：会话会退回上游镜像 ghcr.io/usestrix/strix-sandbox:1.3.0
# （含 Caido 与 Kali 工具链），只是缺少上面那批定制工具与技能资源。
# 构建成功会自动写入 .ravenholt/config.json 的 sandbox.image，让会话改用一体化镜像。
STRIX_DEFAULT_IMAGE="ghcr.io/usestrix/strix-sandbox:1.3.0"
if ! have docker || ! docker info >/dev/null 2>&1; then
  warn "Docker 不可用，跳过沙箱镜像（安装/启动 Docker 后执行：cd sandbox && bash build.sh）"
else
  if docker image inspect "$STRIX_DEFAULT_IMAGE" >/dev/null 2>&1; then
    ok "上游沙箱镜像已存在：$STRIX_DEFAULT_IMAGE"
  else
    info "上游沙箱镜像尚未拉取（首次会话自动拉取，约 4GB）：$STRIX_DEFAULT_IMAGE"
  fi

  if docker image inspect sandbox-runtime:latest >/dev/null 2>&1; then
    ok "一体化沙箱镜像已存在：sandbox-runtime:latest"
    pin_sandbox_image "sandbox-runtime:latest"
  elif [ "$ARCH" != "x86_64" ] && [ "$ARCH" != "amd64" ]; then
    warn "架构 $ARCH 无法构建一体化镜像（仅 x64）：会话沿用上游镜像；平台「沙箱容器」控制台将无终端/文件/noVNC"
  elif [ "$WITH_SANDBOX" -eq 1 ]; then
    info "构建一体化沙箱镜像（下载量大、耗时长，请耐心等待）..."
    if ( cd "$PROJECT_DIR/sandbox" && bash build.sh ); then
      ok "一体化沙箱镜像构建完成：sandbox-runtime:latest"
      pin_sandbox_image "sandbox-runtime:latest"
    else
      warn "一体化沙箱镜像构建失败，会话将继续沿用上游镜像"
      info "镜像构建要先拉取 Docker Hub（debian / golang）与 GHCR（usestrix/strix-sandbox）基础镜像；"
      info "若卡在拉取阶段，请给 Docker 配镜像加速（/etc/docker/daemon.json 的 registry-mirrors）后重试，"
      info "或在能联网的机器上 docker save 后本机 docker load（见 README 常见问题）。"
      info "单独重试构建：cd sandbox && bash build.sh"
    fi
  else
    info "一体化沙箱镜像 sandbox-runtime:latest 未构建 —— 本次不影响渗透可用性"
    info "会话将使用上游镜像（含 Caido 抓包 + Kali 工具链）；构建后额外获得"
    info "Ghidra / Jadx / apktool / binwalk / observer_ward / agent-browser 与技能资源"
    info "构建：cd sandbox && bash build.sh   （或本次运行加 --with-sandbox 自动构建）"
  fi
fi

# ============================================================
# 8. 安装后自检
# ============================================================
step "8/8 安装后自检"
PY="$VENV_DIR/bin/python"
info "语法编译检查..."
if "$PY" -m compileall -q \
     "$PROJECT_DIR/core" "$PROJECT_DIR/service" "$PROJECT_DIR/handler" \
     "$PROJECT_DIR/router" "$PROJECT_DIR/schema" "$PROJECT_DIR/model" \
     "$PROJECT_DIR/middleware" "$PROJECT_DIR/utils" "$PROJECT_DIR"/*.py >/dev/null 2>&1; then
  ok "语法编译通过"
else
  warn "存在语法错误（请查看：$PY -m compileall core service handler router schema model middleware utils app.py main.py config.py database.py logger.py）"
fi

info "配置加载自检..."
"$PY" -c "from config import get_config; get_config()" >/dev/null 2>&1 \
  && ok "config.json 可加载" || warn "config.json 加载失败，请检查其结构"

info "红线策略加载自检（fail-closed）..."
"$PY" -c "from core.policy import load_policy; load_policy()" >/dev/null 2>&1 \
  && ok "policy.yaml 可加载" || warn "policy.yaml 加载失败 —— 平台将拒绝启动，请检查 .ravenholt/policy.yaml"

info "应用装配冒烟（create_app）..."
if "$PY" -c "from app import create_app; create_app()" >/dev/null 2>&1; then
  ok "应用可正常装配（import 链完整）"
else
  warn "create_app 冒烟失败，请手动执行查看报错：$PY -c 'from app import create_app; create_app()'"
fi

# ============================================================
# 收尾
# ============================================================
printf "\n${C_BLU}══ 部署完成${C_NC}\n"
if [ -n "${ADMIN_EMAIL:-}" ] && [ -n "${ADMIN_PWD:-}" ]; then
  printf "  管理员登录： %s / %s\n" "$ADMIN_EMAIL" "$ADMIN_PWD"
  printf "  ${C_YEL}该口令仅在此处显示一次，请立即保存。${C_NC}\n"
else
  printf "  管理员账号： 见 .ravenholt/config.json（system.bootstrap_admin）\n"
fi
printf "  配置文件：   .ravenholt/config.json\n"
printf "  访问地址：   http://127.0.0.1:8000\n"
printf "  启动方式：   bash serve.sh start  （后台常驻，推荐；启动时打印管理员账号口令）\n"
printf "               bash serve.sh run    （前台运行，Ctrl+C 停止）\n"
printf "  停止服务：   bash serve.sh stop\n"
printf "  配置 API Key： bash config-tool.sh set <你的Key> --url <API地址> --model <模型名>\n"
printf "\n"
printf "  ${C_YEL}下一步：编辑 .ravenholt/config.json 的 agents.* 填入 api_key / base_url / model，${C_NC}\n"
printf "  ${C_YEL}然后 bash serve.sh start 即可进入 http://127.0.0.1:8000 使用。${C_NC}\n"
printf "\n"
