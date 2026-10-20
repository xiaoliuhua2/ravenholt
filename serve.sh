#!/usr/bin/env bash
# ============================================================
# Ravenholt - 服务管理脚本（已合并原 start.sh）
#
#   ./serve.sh start     后台启动（默认动作）
#   ./serve.sh stop      停止
#   ./serve.sh restart   重启
#   ./serve.sh status    查看状态（进程 / 端口 / 健康检查）
#   ./serve.sh logs [N]  查看日志（默认 40 行；用 -f 持续跟踪）
#   ./serve.sh run       前台运行（调试用，Ctrl+C 停止）
#
# 行为：
#   - 启动时打印管理员账号与口令（读自 .ravenholt/config.json，便于首次登录）；
#   - 虚拟环境缺失时自动创建并安装依赖（首次较慢）；
#   - Postgres 启动按已安装的主版本号动态探测，不再硬编码版本。
# 后台常驻带 PID 文件、端口健康检查与日志落盘，可反复启停；
# 停止时发 SIGTERM，让 uvicorn 走完整关闭流程（不会留下半途的会话状态）。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
PIP_INDEX="https://mirrors.aliyun.com/pypi/simple/"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/serve.log"
PID_FILE="$LOG_DIR/serve.pid"
# 健康检查地址跟随 config.json 的监听端口/地址（部署者改过 listen_port 时不再误判成"已就绪"）
CFG_LISTEN="$(python3 - "$PROJECT_DIR/.ravenholt/config.json" 2>/dev/null <<'PYEOF' || echo "127.0.0.1 8000"
import json, sys
host, port = "127.0.0.1", 8000
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8")).get("system", {}) or {}
    host = str(cfg.get("listen_addr") or "").strip() or "127.0.0.1"
    port = int(cfg.get("listen_port") or 8000)
except Exception:
    pass
if host in ("0.0.0.0", "::", "*", ""):
    host = "127.0.0.1"
print(f"{host} {port}")
PYEOF
)"
HEALTH_HOST="${CFG_LISTEN%% *}"
HEALTH_PORT="${CFG_LISTEN##* }"
HEALTH_URL="http://${HEALTH_HOST:-127.0.0.1}:${HEALTH_PORT:-8000}/"
READY_TIMEOUT=60

mkdir -p "$LOG_DIR"

info() { printf '%s\n' "$*"; }
fail() { printf '%s\n' "$*" >&2; }

pid_of() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s' "$pid"
}

start_postgres() {
  if pg_isready -q 2>/dev/null; then
    info "  PostgreSQL 已在运行"
    return 0
  fi
  # 动态探测已安装的 PostgreSQL 主版本号（如 16、18）
  local ver
  ver="$(ls /etc/postgresql 2>/dev/null | sort -n | tail -1)"
  info "  启动 PostgreSQL..."
  if [ -n "$ver" ]; then
    systemctl start postgresql 2>/dev/null \
      || pg_ctlcluster "$ver" main start 2>/dev/null \
      || service postgresql start 2>/dev/null
  else
    systemctl start postgresql 2>/dev/null \
      || service postgresql start 2>/dev/null
  fi
  sleep 2
  if pg_isready -q 2>/dev/null; then
    info "  PostgreSQL 启动成功"
    return 0
  fi
  fail "  PostgreSQL 启动失败，请手动执行：systemctl start postgresql"
  return 1
}

ensure_venv() {
  if [ -x "$VENV_DIR/bin/python" ]; then
    return 0
  fi
  info "  未找到虚拟环境，正在创建并安装依赖（首次会下载若干 MB；成功只打印一行，失败会打印完整日志）..."
  if ! python3 -m venv "$VENV_DIR"; then
    fail "  创建虚拟环境失败（请确认已安装 python3-venv）"
    return 1
  fi
  # -q 静默：避免把几十行 "Requirement already satisfied: ..." 刷到屏幕上；失败时再打印完整日志
  "$VENV_DIR/bin/pip" install -q --no-input -i "$PIP_INDEX" --upgrade pip || true
  if "$VENV_DIR/bin/pip" install -q --no-input -i "$PIP_INDEX" -r "$PROJECT_DIR/requirements.txt" > "$LOG_DIR/pip.log" 2>&1; then
    rm -f "$LOG_DIR/pip.log"
    info "  依赖安装完成"
    return 0
  fi
  fail "  依赖安装失败，完整输出如下："
  cat "$LOG_DIR/pip.log" >&2
  fail "  （可换源后重试，例如：pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/）"
  return 1
}

ensure_sandbox_network() {
  local script="$PROJECT_DIR/sandbox/setup_macvlan.sh"
  if [ ! -f "$script" ]; then
    return 0
  fi
  info "  准备沙箱网络（macvlan，按当前宿主自动派生）..."
  if ! bash "$script"; then
    fail "  沙箱网络未就绪，平台将回退默认 bridge 网络"
  fi
  return 0
}

print_admin_credentials() {
  [ -f "$PROJECT_DIR/.ravenholt/config.json" ] || return 0
  local creds email pwd
  creds="$(python3 - <<'PYEOF'
import json
import sys

try:
    with open(".ravenholt/config.json", encoding="utf-8") as fh:
        cfg = json.load(fh)
except Exception:
    sys.exit(0)

adm = (cfg.get("system") or {}).get("bootstrap_admin") or {}
if adm.get("enabled", True):
    print(adm.get("email") or adm.get("username") or "-")
    print(adm.get("password") or "-")
PYEOF
)"
  email="$(printf '%s' "$creds" | sed -n '1p')"
  pwd="$(printf '%s' "$creds" | sed -n '2p')"
  if [ -n "$email" ]; then
    info "  管理员账号：$email"
    info "  管理员口令：$pwd"
  fi
}

do_start() {
  local pid
  if pid="$(pid_of)"; then
    info "服务已在运行（PID $pid）。需要重启请用：./serve.sh restart"
    return 0
  fi

  start_postgres || return 1
  ensure_venv || return 1
  ensure_sandbox_network

  info "  启动后端（后台常驻）..."
  : >> "$LOG_FILE"
  nohup "$VENV_DIR/bin/python" main.py >> "$LOG_FILE" 2>&1 &
  pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"

  info "  等待服务就绪（最多 ${READY_TIMEOUT}s）..."
  local waited=0
  while [ "$waited" -lt "$READY_TIMEOUT" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      fail "  进程已退出，启动失败。日志尾部："
      tail -n 20 "$LOG_FILE" >&2
      rm -f "$PID_FILE"
      return 1
    fi
    if curl -sf -m 2 -o /dev/null "$HEALTH_URL"; then
      info "  服务已就绪"
      print_admin_credentials
      do_status
      return 0
    fi
    sleep 2
    waited=$((waited + 2))
  done

  fail "  等待超时，服务可能仍在启动中。查看日志：./serve.sh logs"
  return 1
}

do_stop() {
  local pid
  if ! pid="$(pid_of)"; then
    info "服务未在运行。"
    rm -f "$PID_FILE"
    return 0
  fi

  info "  停止服务（PID $pid，SIGTERM）..."
  kill "$pid" 2>/dev/null

  local waited=0
  while [ "$waited" -lt 30 ] && kill -0 "$pid" 2>/dev/null; do
    sleep 1
    waited=$((waited + 1))
  done

  if kill -0 "$pid" 2>/dev/null; then
    info "  优雅停止超时，强制结束（SIGKILL）"
    kill -9 "$pid" 2>/dev/null
    sleep 1
  fi

  rm -f "$PID_FILE"
  info "  已停止"
}

do_status() {
  local pid
  if pid="$(pid_of)"; then
    info "进程：运行中（PID $pid）"
  else
    info "进程：未运行"
  fi

  if ss -ltn 2>/dev/null | grep -q ":${HEALTH_PORT}"; then
    info "端口：${HEALTH_PORT} 已监听"
  else
    info "端口：${HEALTH_PORT} 未监听"
  fi

  if curl -sf -m 3 -o /dev/null "$HEALTH_URL"; then
    info "健康检查：通过（$HEALTH_URL 返回 200）"
  else
    info "健康检查：未通过"
  fi

  info "启动日志：$LOG_FILE"
  info "应用日志：$PROJECT_DIR/.ravenholt/app.log"
}

do_logs() {
  local arg="${1:-40}"
  if [ ! -f "$LOG_FILE" ]; then
    info "暂无日志：$LOG_FILE"
    return 0
  fi
  if [ "$arg" = "-f" ]; then
    tail -f "$LOG_FILE"
  else
    tail -n "$arg" "$LOG_FILE"
  fi
}

do_run() {
  start_postgres || exit 1
  ensure_venv || exit 1
  ensure_sandbox_network
  info ""
  info "  前台运行：${HEALTH_URL}"
  info "  API 文档：${HEALTH_URL}docs"
  print_admin_credentials
  info ""
  info "  按 Ctrl+C 停止服务"
  exec "$VENV_DIR/bin/python" main.py
}

case "${1:-start}" in
  start)
    do_start
    ;;
  stop)
    do_stop
    ;;
  restart)
    do_stop
    do_start
    ;;
  status)
    do_status
    ;;
  logs)
    do_logs "${2:-40}"
    ;;
  run)
    do_run
    ;;
  *)
    info "用法：./serve.sh {start|stop|restart|status|logs [行数|-f]|run}"
    exit 2
    ;;
esac
