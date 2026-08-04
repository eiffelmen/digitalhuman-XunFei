#!/usr/bin/env bash

# Collect machine-level diagnostics for long-running browser/WebRTC crashes.
# Usage:
#   bash scripts/monitor_system.sh [interval_seconds] [output_dir]
#
# Example:
#   nohup bash scripts/monitor_system.sh 10 logs > logs/system_monitor.nohup 2>&1 &

set -u

INTERVAL="${1:-10}"
OUT_DIR="${2:-logs}"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="$OUT_DIR/system_monitor_${TS}.log"

run_section() {
  local title="$1"
  shift
  {
    echo
    echo "===== ${title} ====="
    "$@" 2>&1 || true
  } >> "$OUT_FILE"
}

run_shell_section() {
  local title="$1"
  local cmd="$2"
  {
    echo
    echo "===== ${title} ====="
    bash -lc "$cmd" 2>&1 || true
  } >> "$OUT_FILE"
}

echo "system monitor started at $(date -Is)" | tee -a "$OUT_FILE"
echo "interval_seconds=${INTERVAL}" | tee -a "$OUT_FILE"
echo "output_file=${OUT_FILE}" | tee -a "$OUT_FILE"

while true; do
  {
    echo
    echo "################################################################"
    echo "timestamp=$(date -Is)"
    echo "uptime=$(uptime 2>/dev/null || true)"
  } >> "$OUT_FILE"

  run_section "free -m" free -m
  run_section "df -h" df -h
  run_section "vmstat 1 2" vmstat 1 2

  run_shell_section "top rss processes" \
    "ps -eo pid,ppid,%cpu,%mem,rss,vsz,etime,stat,comm,args --sort=-rss | head -40"

  run_shell_section "digital-human backend processes" \
    "ps -eo pid,ppid,%cpu,%mem,rss,vsz,etime,stat,comm,args | grep -E 'app_v2.py|realtime-digital-human|digitalhuman-Xinjiang|uv run python|python .*app_v2' | grep -v grep"

  run_shell_section "chrome processes" \
    "ps -eo pid,ppid,%cpu,%mem,rss,vsz,etime,stat,comm,args | grep -E 'chrome|Chrome|chromium' | grep -v grep | sort -k5 -nr | head -40"

  run_shell_section "chrome renderer/gpu process counts" \
    "printf 'chrome_total='; pgrep -af 'chrome|Chrome|chromium' | wc -l; printf 'renderer='; pgrep -af -- '--type=renderer' | wc -l; printf 'gpu_process='; pgrep -af -- '--type=gpu-process' | wc -l"

  run_shell_section "backend proc details" \
    "for pid in \$(pgrep -f 'app_v2.py|python .*app_v2' | sort -u); do echo '--- pid='\"\$pid\"; cat /proc/\"\$pid\"/status 2>/dev/null | grep -E 'Name|State|VmRSS|VmHWM|VmSize|VmData|VmSwap|Threads|FDSize'; printf 'open_fds='; ls /proc/\"\$pid\"/fd 2>/dev/null | wc -l; done"

  run_shell_section "chrome proc details top rss" \
    "for pid in \$(ps -eo pid,rss,args | grep -E 'chrome|Chrome|chromium' | grep -v grep | sort -k2 -nr | head -8 | awk '{print \$1}'); do echo '--- pid='\"\$pid\"; cat /proc/\"\$pid\"/status 2>/dev/null | grep -E 'Name|State|VmRSS|VmHWM|VmSize|VmData|VmSwap|Threads|FDSize'; printf 'open_fds='; ls /proc/\"\$pid\"/fd 2>/dev/null | wc -l; done"

  if command -v nvidia-smi >/dev/null 2>&1; then
    run_section "nvidia-smi" nvidia-smi
    run_shell_section "nvidia-smi process query" \
      "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits 2>/dev/null || true; nvidia-smi --query-gpu=timestamp,name,driver_version,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,power.draw --format=csv 2>/dev/null || true"
  else
    run_shell_section "nvidia-smi" "echo 'nvidia-smi not found'"
  fi

  if command -v docker >/dev/null 2>&1; then
    run_shell_section "docker ps" "docker ps --no-trunc 2>&1"
    run_shell_section "docker stats" "docker stats --no-stream 2>&1"
  else
    run_shell_section "docker" "echo 'docker not found'"
  fi

  run_shell_section "network listeners" \
    "ss -tulpn 2>/dev/null | grep -E ':80 |:443 |:8010 |:8000 |:10099 ' || true"

  sync "$OUT_FILE" 2>/dev/null || true
  sleep "$INTERVAL"
done
