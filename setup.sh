#!/usr/bin/env bash
# ============================================================
# Ravenholt 一键部署脚本
#
#   环境检测 → 系统依赖 → 配置初始化 → PostgreSQL → Python 依赖
#   → 前端构建 → 沙箱镜像(可选) → 安装后自检
#
# 适用环境：Linux x64（推荐 Kali / Debian）
# 用法：
#   bash setup.sh                 # 检测 + 安装 + 部署
#   bash setup.sh --check         # 仅环境检测，不改动任何文件
#   bash setup.sh --with-sandbox  # 额外自动构建沙箱镜像（下载量大、耗时长）
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
  bash setup.sh                 检测 + 安装 + 部署
  bash setup.sh --check         仅环境检测，不改动任何文件
  bash setup.sh --with-sandbox  额外自动构建沙箱镜像（下载量大、耗时长）
  bash setup.sh -h | --help     显示本帮助

说明：更新替代，已存在的 .ravenholt/config.json、policy.yaml 不会被覆盖。
EOF
}

CHECK_ONLY=0
WITH_SANDBOX=0
for arg in "$@"; do
  case "$arg" in
    --check|-c)      CHECK_ONLY=1 ;;
    --with-sandbox)  WITH_SANDBOX=1 ;;
    -h|--help)       usage; exit 0 ;;
    *) printf "未知参数: %s（可用: --check / --with-sandbox / --help）\n" "$arg"; exit 2 ;;
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
  if [ "$(id -u)" -eq 0 ]; then
    su -s /bin/sh -c "$(printf '%q ' psql "$@")" postgres
  elif have sudo; then
    sudo -n -u postgres psql "$@"
  else
    return 127
  fi
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
  if node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit((a>20)||(a===20&&b>=19)?0:1)' 2>/dev/null; then
    ok "Node.js: $NODEV"
  else
    warn "Node.js: $NODEV —— 前端构建需要 >= 20.19（推荐 22+）"
    info "升级：curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
  fi
  have npm && ok "npm: $(npm -v 2>/dev/null)" || warn "npm 未找到（通常随 nodejs 一起安装）"
else
  warn "Node.js 未安装 —— 前端无法构建；建议用 nodesource 安装 22+："
  info "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"
fi

# 1.5 Docker（渗透沙箱运行时；缺失则功能受限）
if have docker; then
  ok "Docker: $(docker --version 2>/dev/null | sed 's/^Docker version //;s/,.*//')"
  if docker compose version >/dev/null 2>&1 || have docker-compose; then
    ok "Docker Compose 可用"
  else
    warn "Docker Compose 未找到（docker-compose.prod.yml 需要）"
  fi
  docker info >/dev/null 2>&1 || warn "Docker 守护进程未运行（systemctl start docker）"
else
  warn "Docker 未安装 —— 渗透/代码审计沙箱功能将不可用"
  info "安装：sudo apt install -y docker.io && sudo systemctl enable --now docker"
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
    if "${APT[@]}" update -qq && "${APT[@]}" install -y $PKGS 2>&1 | tail -5; then
      ok "系统依赖已安装"
    else
      warn "apt 安装未完成，请手动执行：sudo apt install -y $PKGS"
    fi
  fi
else
  ok "系统依赖已就绪"
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
info "pip 安装依赖（阿里云镜像）..."
"$PY" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ --upgrade pip -q 2>&1 | tail -1
# 注意：这里依赖脚本顶部的 pipefail，管道退出码才能正确反映 pip 是否失败
if "$PY" -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r "$PROJECT_DIR/requirements.txt" 2>&1 | tail -3; then
  ok "Python 依赖已安装（requirements.txt）"
else
  fatal "Python 依赖安装失败，请检查网络/镜像后重跑本脚本"
fi

# ============================================================
# 6. 前端构建
# ============================================================
step "6/8 构建前端"
if [ -d "$PROJECT_DIR/web" ]; then
  if ! have node; then
    warn "未安装 Node.js，跳过前端构建（后端仍可跑，但界面缺失）"
  else
    cd "$PROJECT_DIR/web"
    # web/openapi.json 已随仓库提交；缺失时回退根 openapi.json
    if [ ! -f "$PROJECT_DIR/web/openapi.json" ] && [ -f "$PROJECT_DIR/openapi.json" ]; then
      ln -sf "$PROJECT_DIR/openapi.json" "$PROJECT_DIR/web/openapi.json"
      info "已链接 web/openapi.json -> openapi.json"
    fi
    if [ ! -d node_modules/openapi-typescript ] || [ ! -d node_modules/vite ]; then
      info "npm install ..."
      if ! npm install > "$PROJECT_DIR/web/.npm-install.log" 2>&1; then
        tail -20 "$PROJECT_DIR/web/.npm-install.log"; rm -f "$PROJECT_DIR/web/.npm-install.log"
        warn "npm install 失败，跳过前端构建"
      else
        rm -f "$PROJECT_DIR/web/.npm-install.log"; ok "前端依赖已安装"
      fi
    else
      ok "前端依赖已就绪"
    fi
    if [ -d node_modules/vite ]; then
      info "npm run build（generate:api → tsc → vite build）..."
      if npm run build > "$PROJECT_DIR/web/.build.log" 2>&1; then
        tail -2 "$PROJECT_DIR/web/.build.log"; ok "前端构建完成：web/dist-app"
      else
        tail -25 "$PROJECT_DIR/web/.build.log"; warn "前端构建失败，请检查上方日志"
      fi
      rm -f "$PROJECT_DIR/web/.build.log"
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
if ! have docker; then
  warn "未安装 Docker，跳过（安装 Docker 后执行：cd sandbox && bash build.sh）"
elif ! docker info >/dev/null 2>&1; then
  warn "Docker 守护进程未运行，跳过（启动后执行：cd sandbox && bash build.sh）"
elif [ "$ARCH" != "x86_64" ] && [ "$ARCH" != "amd64" ]; then
  warn "架构 $ARCH 不支持沙箱镜像构建（仅 x64）"
elif docker image inspect sandbox-runtime:latest >/dev/null 2>&1; then
  ok "沙箱镜像 sandbox-runtime:latest 已存在"
elif [ "$WITH_SANDBOX" -eq 1 ]; then
  info "构建沙箱镜像（下载量大、耗时长，请耐心等待）..."
  ( cd "$PROJECT_DIR/sandbox" && bash build.sh ) && ok "沙箱镜像构建完成" || warn "沙箱镜像构建失败"
else
  info "沙箱镜像 sandbox-runtime:latest 未构建 —— 渗透/审计执行依赖它"
  info "构建：cd sandbox && bash build.sh   （或本次运行加 --with-sandbox 自动构建）"
  info "运行时按会话自动 provision 镜像记录，无需手工登记"
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
printf "  启动方式：   bash start.sh        （前台运行）\n"
printf "               bash serve.sh start  （后台常驻，推荐）\n"
printf "  停止服务：   bash serve.sh stop\n"
printf "  配置 API Key： bash config-tool.sh set <你的Key> --url <API地址> --model <模型名>\n"
printf "\n"
printf "  ${C_YEL}下一步：编辑 .ravenholt/config.json 的 agents.* 填入 api_key / base_url / model，${C_NC}\n"
printf "  ${C_YEL}然后 bash start.sh 即可进入 http://127.0.0.1:8000 使用。${C_NC}\n"
printf "\n"
