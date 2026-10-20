#!/usr/bin/env bash
# ============================================================
# Ravenholt 一键升级
#
#   bash update.sh                     拉取最新代码 → 更新依赖 → 重启服务
#   bash update.sh --no-pull           不拉代码，只按当前代码重建依赖并重启
#   bash update.sh --rebuild-frontend  强制重建前端产物（web/dist-app）
#   bash update.sh --with-sandbox      额外重建一体化沙箱镜像（下载量大、耗时长）
#
# 复用 setup.sh 的幂等逻辑：pip 已满足则跳过、前端产物已存在则跳过、
# 已存在的 config.json / policy.yaml 一律不覆盖。因此可以放心反复执行。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

PULL=1
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --no-pull)          PULL=0 ;;
    --rebuild-frontend) EXTRA+=(--rebuild-frontend) ;;
    --with-sandbox)     EXTRA+=(--with-sandbox) ;;
    -h|--help)          sed -n '2,12p' "$0"; exit 0 ;;
    *) printf "未知参数: %s（可用: --no-pull / --rebuild-frontend / --with-sandbox / --help）\n" "$arg"; exit 2 ;;
  esac
done

info() { printf '  · %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }

echo
echo "══ Ravenholt 升级"

# ── 1. 拉取代码 ─────────────────────────────────────────────
if [ "$PULL" -eq 1 ]; then
  if [ -d "$PROJECT_DIR/.git" ]; then
    info "git pull --ff-only ..."
    # 有本地改动时 --ff-only 会失败：只提示，不覆盖用户的改动
    if ! git -C "$PROJECT_DIR" pull --ff-only; then
      warn "代码拉取未完成（本地有改动或网络不通）—— 继续用当前代码升级"
    fi
  else
    info "当前目录不是 git 仓库，跳过代码拉取"
  fi
fi

# ── 2. 更新依赖 + 安装后自检 ────────────────────────────────
# --no-deps：跳过系统依赖与 Node.js / Docker 的自动安装，只做 Python 依赖、
# 前端产物与自检；这些步骤都是幂等的，已就绪的会直接跳过。
info "更新 Python 依赖 / 前端产物，并执行安装后自检 ..."
if ! bash "$PROJECT_DIR/setup.sh" --no-deps "${EXTRA[@]+"${EXTRA[@]}"}"; then
  warn "setup.sh 未正常完成（见上方输出）"
  warn "若只是前端构建失败，可单独重试： cd web && npm install --include=optional && npm run build"
  exit 1
fi

# ── 3. 重启服务 ─────────────────────────────────────────────
info "重启服务 ..."
bash "$PROJECT_DIR/serve.sh" restart
