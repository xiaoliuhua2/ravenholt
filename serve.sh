#!/usr/bin/env bash
# ============================================================
# Ravenholt - 后台常驻服务管理脚本
#
#   ./serve.sh start     后台启动（默认动作）
#   ./serve.sh stop      停止
#   ./serve.sh restart   重启
#   ./serve.sh status    查看状态（进程 / 端口 / 健康检查）
#   ./serve.sh logs [N]  查看日志（默认 40 行；用 -f 持续跟踪）
#   ./serve.sh run       前台运行（调试用，Ctrl+C 停止）
#
# 与 start.sh 的区别：start.sh 是前台一次性启动，关掉终端就中断；
# 本脚本后台常驻，带 PID 文件、端口健康检查与日志落盘，可反复启停。
# 停止时发 SIGTERM，让 uvicorn 走完整关闭流程（不会留下半途的会话状态）。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/serve.log"
PID_FILE="$LOG_DIR/serve.pid"
HEALTH_URL="http://127.0.0.1:8000/"
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

ensure_postgres() {
  if pg_isready -q 2>/dev/null; then
    info "  PostgreSQL 已在运行"
    return 0
  fi
  info "  启动 PostgreSQL..."
  systemctl start postgresql 2>/dev/null \
    || pg_ctlcluster 18 main start 2>/dev/null \
    || service postgresql start 2>/dev/null
  sleep 2
  if pg_isready -q 2>/dev/null; then
    info "  PostgreSQL 启动成功"
    return 0
  fi
  fail "  PostgreSQL 启动失败，请手动执行：systemctl start postgresql"
  return 1
}

ensure_venv() {
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    fail "  找不到虚拟环境：$VENV_DIR/bin/python"
    fail "  请先执行：cd $PROJECT_DIR && bash setup.sh"
    return 1
  fi
  return 0
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

do_start() {
  local pid
  if pid="$(pid_of)"; then
    info "服务已在运行（PID $pid）。需要重启请用：./serve.sh restart"
    return 0
  fi

  ensure_postgres || return 1
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

  if ss -ltn 2>/dev/null | grep -q ':8000'; then
    info "端口：8000 已监听"
  else
    info "端口：8000 未监听"
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
    ensure_postgres || exit 1
    ensure_venv || exit 1
    exec "$VENV_DIR/bin/python" main.py
    ;;
  *)
    info "用法：./serve.sh {start|stop|restart|status|logs [行数|-f]|run}"
    exit 2
    ;;
esac
