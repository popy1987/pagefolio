#!/usr/bin/env bash
#
# Pagefolio 服务管理脚本（一键 restart）
#
#   ./serve.sh            # 无参 = restart（一键重启）
#   ./serve.sh restart    # 同上
#   ./serve.sh start      # 仅启动（已在运行则提示）
#   ./serve.sh stop       # 停止
#   ./serve.sh status     # 查看运行状态
#   ./serve.sh logs       # 跟踪日志（Ctrl-C 退出）
#
set -euo pipefail

# ---- 路径与常量（脚本放在项目根目录，可在任意目录调用）----
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8765}"
HOST="127.0.0.1"
PID_FILE="$ROOT/.pagefolio.pid"
LOG_FILE="/tmp/pagefolio_serve.log"
HEALTH_URL="http://$HOST:$PORT/api/years"
PY_BIN="${PYTHON:-python3}"

c_green=$'\033[32m'; c_red=$'\033[31m'; c_yellow=$'\033[33m'; c_reset=$'\033[0m'
ok()   { echo "${c_green}✔${c_reset} $*"; }
warn() { echo "${c_yellow}!${c_reset} $*"; }
err()  { echo "${c_red}✘${c_reset} $*" >&2; }

# 占用端口的 PID（可能有多个）
port_pids() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true; }

# PID 文件记录的进程是否存活且确实是本服务
alive_pid() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && \
    ps -p "$pid" -o command= 2>/dev/null | grep -q "run.py serve"
}

# ---- stop ----
do_stop() {
  local stopped=0

  # 1) PID 文件优先（本脚本启动的进程）
  if [ -f "$PID_FILE" ]; then
    local pid; pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if alive_pid "$pid"; then
      kill "$pid" 2>/dev/null || true
      for _ in $(seq 1 10); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
      if kill -0 "$pid" 2>/dev/null; then kill -9 "$pid" 2>/dev/null || true; fi
      ok "已停止进程 PID ${pid}（PID 文件）"
      stopped=1
    fi
    rm -f "$PID_FILE"
  fi

  # 2) 端口兜底（旧版/手动启动、PID 文件丢失的残留进程）
  local pids; pids="$(port_pids)"
  if [ -n "$pids" ]; then
    echo "$pids" | while read -r pid; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
    sleep 1
    pids="$(port_pids)"
    if [ -n "$pids" ]; then
      echo "$pids" | while read -r pid; do [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true; done
      sleep 1
    fi
    ok "已清理占用端口 $PORT 的残留进程"
    stopped=1
  fi

  [ "$stopped" -eq 1 ] || warn "没有运行中的 Pagefolio 服务"
}

# ---- start ----
do_start() {
  if [ -n "$(port_pids)" ]; then
    warn "端口 $PORT 已有服务在运行（PID: $(port_pids | tr '\n' ' ')），如需重启请用 ./serve.sh restart"
    return 0
  fi

  cd "$ROOT"
  : > "$LOG_FILE"
  nohup "$PY_BIN" run.py serve > "$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"

  # 等待端口 LISTEN
  local ready=0
  for _ in $(seq 1 20); do
    if [ -n "$(port_pids)" ]; then ready=1; break; fi
    # 进程提前退出则报错
    if ! kill -0 "$pid" 2>/dev/null; then
      err "服务启动失败，日志尾部："
      tail -15 "$LOG_FILE" >&2
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 0.5
  done

  if [ "$ready" -ne 1 ]; then
    err "等待端口 $PORT 超时，日志尾部："
    tail -15 "$LOG_FILE" >&2
    return 1
  fi

  # HTTP 链路健康检查（能返回 200 JSON 即正常）
  local code; code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
  if [ "$code" = "200" ]; then
    ok "服务已启动  PID $pid  →  http://$HOST:$PORT"
  else
    warn "端口已监听但健康检查返回 HTTP ${code}（详见 $LOG_FILE）"
  fi
}

# ---- status ----
do_status() {
  local pid=""
  [ -f "$PID_FILE" ] && pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  local pids; pids="$(port_pids)"

  if [ -n "$pids" ]; then
    ok "运行中  监听 PID: $(echo "$pids" | tr '\n' ' ')"
    [ -n "$pid" ] && echo "        PID 文件: $pid"
    local code; code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo 000)"
    [ "$code" = "200" ] && ok "健康检查 HTTP 200  →  http://$HOST:$PORT" \
                          || warn "健康检查 HTTP $code"
    echo "        日志: $LOG_FILE"
  else
    warn "未运行（端口 $PORT 无监听）"
    return 1
  fi
}

# ---- 分发 ----
case "${1:-restart}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  logs)    tail -f "$LOG_FILE" ;;
  *)
    echo "用法: ./serve.sh [start|stop|restart|status|logs]（无参 = restart）" >&2
    exit 1 ;;
esac
