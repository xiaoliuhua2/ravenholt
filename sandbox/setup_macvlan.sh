#!/usr/bin/env bash
# ============================================================
# Ravenholt - 沙箱 macvlan 网络：按当前宿主自动派生 + 幂等自愈
#
# 作用：给沙箱容器一个**局域网内独立 IP**，使被评测目标可以主动回连
#       （反弹 shell / OOB 外带）。macvlan 容器与宿主天生隔离，故同时建立
#       宿主侧 shim 接口 + 指向容器地址段的精确路由，保证平台进程仍能访问
#       容器内 Caido。
#
# 幂等：可反复执行，行为稳定。
#   - 网络已存在且网段 / 网关 / 父接口 / 容器段与当前宿主一致 → 只补齐 shim 与路由。
#   - 网段漂移（宿主换网段 / 换网络）→ 断开旧容器并重建网络 + shim + 路由。
#   - 首次 → 自动扫描选取空闲容器段与 shim 地址后建立。
#
# 不写死任何网段：parent / 子网 / 网关从宿主默认路由与网卡派生；容器段与 shim
# 地址由在线扫描选空闲值。
#
# 失败**不修改 config**：宿主或云不支持 macvlan（禁伪造 MAC / 禁 L2 多 MAC）时
# 直接退出，平台启动时会检测到网络缺失并自动回退默认 bridge（见 main.py），
# OOB 外带走容器内已预装的 interactsh。
#
# 由 serve.sh start 调用；也可手动执行。需要 root。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
PROJECT_DIR="$(pwd)"
CONFIG_FILE="$PROJECT_DIR/.ravenholt/config.json"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
PY="$VENV_PY"
[ -x "$PY" ] || PY="$(command -v python3 || true)"

# 宿主 shim 接口名（固定，非网段，避免超长导致 iface 名超 15 字符）
SHIM_NAME="rav-shim"
# 容器地址段大小：/27（每个网络 30 个可用地址）
RANGE_PFX="27"
# 在线扫描上限：子网大于此规模时跳过扫描（避免逐地址 ping）
SWEEP_MAX="1024"

log()  { printf '[sandbox-net] %s\n' "$*"; }
warn() { printf '[sandbox-net] %s\n' "$*" >&2; }

# ---------- 读取配置里的网络名 ----------
read_network() {
  "$PY" - "$CONFIG_FILE" <<'PYEOF'
import json, sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("")
else:
    print((data.get("sandbox") or {}).get("network", "") or "")
PYEOF
}

# ---------- IP 计算 ----------
ip2int() {
  local IFS=.
  read -r a b c d <<<"$1"
  echo $(( (a << 24) | (b << 16) | (c << 8) | d ))
}

int2ip() {
  echo "$(( ($1 >> 24) & 255 )).$(( ($1 >> 16) & 255 )).$(( ($1 >> 8) & 255 )).$(( $1 & 255 ))"
}

# ---------- 在线主机扫描（选空闲段 / 地址用） ----------
declare -A LIVE=()

sweep_online() {
  LIVE=()
  if [ "${SIZE:-0}" -gt "$SWEEP_MAX" ]; then
    warn "子网过大（/$PFX），跳过在线扫描"
    return 0
  fi

  local ip
  if command -v nmap >/dev/null 2>&1; then
    for ip in $(nmap -sn -T4 -oG - "$SUBNET" 2>/dev/null | awk '/^Host:/{print $2}'); do
      LIVE[$ip]=1
    done
    return 0
  fi

  # nmap 缺失时用并发 ping 兜底（在线主机 ICMP 被过滤时可能漏判）
  local tmp i
  tmp="$(mktemp)"
  for ((i = 1; i < SIZE - 1; i++)); do
    ip="$(int2ip $(( NET_VAL + i )))"
    ( ping -c1 -W1 "$ip" >/dev/null 2>&1 && echo "$ip" >>"$tmp" ) &
  done
  wait
  while read -r ip; do
    LIVE[$ip]=1
  done <"$tmp"
  rm -f "$tmp"
}

# ---------- 选一个空闲的容器段（/27），从高地址往低选 ----------
pick_range_cidr() {
  local bs=$(( 1 << (32 - RANGE_PFX) ))
  local count=$(( SIZE / bs ))
  local k base i ip ok
  for ((k = count - 1; k >= 0; k--)); do
    base=$(( NET_VAL + k * bs ))
    ok=1
    for ((i = 1; i < bs - 1; i++)); do
      ip="$(int2ip $(( base + i )))"
      if [ "$ip" = "$GW" ] || [ "$ip" = "$HOST_IP" ] || [ -n "${LIVE[$ip]:-}" ]; then
        ok=0
        break
      fi
    done
    if [ "$ok" = 1 ]; then
      printf '%s/%s\n' "$(int2ip "$base")" "$RANGE_PFX"
      return 0
    fi
  done
  return 1
}

# ---------- 选一个空闲 shim 地址（容器段之外，从高地址往低选） ----------
pick_shim_ip() {
  local rbase="$1" rbs="$2" i v ip
  for ((i = SIZE - 2; i >= 1; i--)); do
    v=$(( NET_VAL + i ))
    if (( v >= rbase && v < rbase + rbs )); then
      continue
    fi
    ip="$(int2ip "$v")"
    [ "$ip" = "$GW" ] && continue
    [ "$ip" = "$HOST_IP" ] && continue
    [ -n "${LIVE[$ip]:-}" ] && continue
    printf '%s\n' "$ip"
    return 0
  done
  return 1
}

in_subnet() {
  local v
  v="$(ip2int "$1")"
  (( v > NET_VAL && v < NET_VAL + SIZE - 1 ))
}

disconnect_containers() {
  local name
  for name in $(docker network inspect -f '{{range .Containers}}{{.Name}} {{end}}' "$NETWORK" 2>/dev/null); do
    docker network disconnect -f "$NETWORK" "$name" >/dev/null 2>&1 || true
  done
}

ensure_shim() {
  if ip link show "$SHIM_NAME" >/dev/null 2>&1; then
    if ! ip -o link show "$SHIM_NAME" 2>/dev/null | grep -q "@$IFACE"; then
      log "shim 父接口已变化，重建 shim"
      ip link del "$SHIM_NAME" >/dev/null 2>&1 || true
    fi
  fi

  if ! ip link show "$SHIM_NAME" >/dev/null 2>&1; then
    ip link add "$SHIM_NAME" link "$IFACE" type macvlan mode bridge || return 1
  fi

  # 清掉与目标不符的旧地址
  local addr cur
  for addr in $(ip -o -4 addr show dev "$SHIM_NAME" 2>/dev/null | awk '{print $4}'); do
    cur="${addr%/*}"
    if [ "$cur" != "$SHIM_IP" ]; then
      ip addr del "$addr" dev "$SHIM_NAME" >/dev/null 2>&1 || true
    fi
  done

  ip addr replace "$SHIM_IP/32" dev "$SHIM_NAME" || return 1
  ip link set "$SHIM_NAME" up || return 1
  ip route replace "$RANGE_CIDR" dev "$SHIM_NAME" src "$SHIM_IP" || return 1
  return 0
}

# ======================= 主流程 =======================
NETWORK="$(read_network)"
NETWORK="${NETWORK//[$'\t\r\n ']/}"
if [ -z "$NETWORK" ]; then
  log "未配置 sandbox.network，跳过（沙箱使用默认 bridge）"
  exit 0
fi

# --- 派生宿主网络 ---
DEF_ROUTE="$(ip -4 route show default 2>/dev/null | head -n1)"
IFACE="$(awk '{for (i = 1; i <= NF; i++) if ($i == "dev") print $(i + 1)}' <<<"$DEF_ROUTE" | head -n1)"
GW="$(awk '{for (i = 1; i <= NF; i++) if ($i == "via") print $(i + 1)}' <<<"$DEF_ROUTE" | head -n1)"
if [ -z "$IFACE" ] || [ -z "$GW" ]; then
  warn "无法从默认路由派生网卡 / 网关，跳过沙箱网络"
  exit 1
fi

ADDR_CIDR="$(ip -o -4 addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | head -n1)"
if [ -z "$ADDR_CIDR" ]; then
  warn "网卡 $IFACE 上没有 IPv4 地址，跳过沙箱网络"
  exit 1
fi
HOST_IP="${ADDR_CIDR%/*}"
PFX="${ADDR_CIDR#*/}"
HOST_VAL="$(ip2int "$HOST_IP")"
MASK=$(( (0xFFFFFFFF << (32 - PFX)) & 0xFFFFFFFF ))
NET_VAL=$(( HOST_VAL & MASK ))
SIZE=$(( 1 << (32 - PFX) ))
SUBNET="$(int2ip "$NET_VAL")/$PFX"
log "宿主网卡=$IFACE 宿主=$ADDR_CIDR 网关=$GW 子网=$SUBNET"

NEED_SWEEP=0
NET_EXISTS=0
RANGE_CIDR=""

# --- 网络是否已存在且与当前宿主一致 ---
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
  NET_EXISTS=1
  CUR_SUBNET="$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}' "$NETWORK" 2>/dev/null)"
  CUR_GW="$(docker network inspect -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' "$NETWORK" 2>/dev/null)"
  CUR_RANGE="$(docker network inspect -f '{{range .IPAM.Config}}{{.IPRange}}{{end}}' "$NETWORK" 2>/dev/null)"
  CUR_PARENT="$(docker network inspect -f '{{index .Options "parent"}}' "$NETWORK" 2>/dev/null)"
  if [ "$CUR_SUBNET" = "$SUBNET" ] && [ "$CUR_GW" = "$GW" ] && [ "$CUR_PARENT" = "$IFACE" ] && [ -n "$CUR_RANGE" ]; then
    RANGE_CIDR="$CUR_RANGE"
    log "网络 $NETWORK 已存在且与当前宿主一致（容器段 $RANGE_CIDR）"
  else
    warn "网络 $NETWORK 与当前宿主不一致（现 $CUR_SUBNET / $CUR_GW / ${CUR_PARENT:-none} / ${CUR_RANGE:-none}），重建"
    disconnect_containers
    docker network rm "$NETWORK" >/dev/null 2>&1 || true
    NET_EXISTS=0
    NEED_SWEEP=1
  fi
fi

# --- 复用还是重选 shim 地址 ---
EXISTING_SHIM_IP="$(ip -o -4 addr show dev "$SHIM_NAME" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)"
SHIM_IP=""
if [ -n "$EXISTING_SHIM_IP" ] && ip -o link show "$SHIM_NAME" 2>/dev/null | grep -q "@$IFACE" && in_subnet "$EXISTING_SHIM_IP"; then
  SHIM_IP="$EXISTING_SHIM_IP"
else
  NEED_SWEEP=1
fi

if [ "$NEED_SWEEP" = 1 ]; then
  sweep_online
fi

if [ -z "$RANGE_CIDR" ]; then
  RANGE_CIDR="$(pick_range_cidr)" || { warn "在 $SUBNET 内找不到空闲的容器地址段"; exit 1; }
fi
RANGE_BASE="$(ip2int "${RANGE_CIDR%/*}")"
RANGE_SIZE=$(( 1 << (32 - ${RANGE_CIDR#*/} ) ))

if [ -z "$SHIM_IP" ]; then
  SHIM_IP="$(pick_shim_ip "$RANGE_BASE" "$RANGE_SIZE")" || { warn "在 $SUBNET 内找不到空闲的 shim 地址"; exit 1; }
fi

# --- 建立网络 ---
if [ "$NET_EXISTS" = 0 ]; then
  if ! docker network create -d macvlan \
    --subnet "$SUBNET" --gateway "$GW" --ip-range "$RANGE_CIDR" \
    -o parent="$IFACE" "$NETWORK"; then
    warn "创建 macvlan 网络失败（宿主或云可能不支持 macvlan，将回退 bridge）"
    exit 1
  fi
  log "已创建网络 $NETWORK（子网 $SUBNET 网关 $GW 容器段 $RANGE_CIDR）"
fi

# --- 建立 shim + 精确路由 ---
if ! ensure_shim; then
  warn "建立宿主 shim / 路由失败，将回退 bridge"
  exit 1
fi

log "就绪：网络=$NETWORK 子网=$SUBNET 网关=$GW 容器段=$RANGE_CIDR shim=$SHIM_IP@$SHIM_NAME"
