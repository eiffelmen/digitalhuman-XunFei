#!/usr/bin/env bash
set -Eeuo pipefail

# Start digitalhuman-XunFei services in the background.
# Run scripts/bootstrap_ubuntu.sh first, then fill /opt/digitalhuman/be/.env.

PROJECT_ROOT="${PROJECT_ROOT:-/opt/digitalhuman}"
BACKEND_DIR="${BACKEND_DIR:-$PROJECT_ROOT/be}"
DEVICE_DIR="${DEVICE_DIR:-$PROJECT_ROOT/device}"
FRONTEND_DIR="${FRONTEND_DIR:-$PROJECT_ROOT/fe}"
CERT_DIR="${CERT_DIR:-/data/prod/fe/certs}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
RUN_DIR="${RUN_DIR:-$PROJECT_ROOT/run}"

BIND_HOST="${BIND_HOST:-0.0.0.0}"
REALTIME_PORT="${REALTIME_PORT:-8010}"
DEVICE_PORT="${DEVICE_PORT:-8000}"
HTTP_PORT="${HTTP_PORT:-80}"
HTTPS_PORT="${HTTPS_PORT:-443}"

FRONTEND_IMAGE="${FRONTEND_IMAGE:-digitalhuman/front:local}"
FRONTEND_CONTAINER="${FRONTEND_CONTAINER:-frontend}"
BUILD_FRONTEND_IMAGE="${BUILD_FRONTEND_IMAGE:-auto}" # auto, 1, 0
PULL_FRONTEND_IMAGE="${PULL_FRONTEND_IMAGE:-0}"
BACKEND_HOST="${BACKEND_HOST:-host.docker.internal}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"

VIDEO_FILE="反诈视频.mp4"

log() {
  printf '\n>>> %s\n' "$*" >&2
}

warn() {
  printf '\n[WARN] %s\n' "$*" >&2
}

die() {
  printf '\n[ERROR] %s\n' "$*" >&2
  exit 1
}

docker_cmd() {
  if docker ps >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

require_file() {
  local path="$1"
  local hint="$2"

  if [ ! -e "$path" ]; then
    die "$path is missing. $hint"
  fi
}

prepare_dirs() {
  mkdir -p "$LOG_DIR" "$RUN_DIR"
}

load_backend_env() {
  if [ -f "$BACKEND_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$BACKEND_DIR/.env"
    set +a
  else
    warn "$BACKEND_DIR/.env is missing. Copy .env.template and fill real API keys before production use."
  fi

  REALTIME_PORT="${LISTEN_PORT:-$REALTIME_PORT}"
  if [ "$REALTIME_PORT" != "8010" ]; then
    warn "LISTEN_PORT=$REALTIME_PORT, but frontend nginx template proxies /backend/ to port 8010. Keep 8010 unless you also update frontend nginx config."
  fi

  if [ -f "$BACKEND_DIR/.env" ] && grep -Eq 'your-|your_' "$BACKEND_DIR/.env"; then
    warn "$BACKEND_DIR/.env still appears to contain placeholder values. LLM/TTS may not work until real keys are filled."
  fi
}

preflight() {
  log "Checking runtime files"
  require_file "$BACKEND_DIR/run_digitalman_server.sh" "Project source is not ready. Run scripts/bootstrap_ubuntu.sh first."
  require_file "$BACKEND_DIR/.venv/bin/python" "Backend dependencies are not installed. Run scripts/bootstrap_ubuntu.sh first."
  require_file "$BACKEND_DIR/wav2lip256/wav2lip.pth" "Missing model weight. Run scripts/bootstrap_ubuntu.sh or place wav2lip.pth manually."
  require_file "$BACKEND_DIR/data/avatars/wav2lip_avatar11/coords.pkl" "Missing avatar data. Unzip data.zip into $BACKEND_DIR/data."
  require_file "$DEVICE_DIR/resources/$VIDEO_FILE" "Missing anti-fraud video. Place it under $DEVICE_DIR/resources."
  require_file "$FRONTEND_DIR/Dockerfile" "Frontend source is missing."
  require_file "$CERT_DIR/service.pem" "Frontend certificate is missing. Run scripts/bootstrap_ubuntu.sh first."
  require_file "$CERT_DIR/service-key.pem" "Frontend private key is missing. Run scripts/bootstrap_ubuntu.sh first."
}

stop_pid_process() {
  local name="$1"
  local pid_file="$RUN_DIR/$name.pid"

  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    log "Stopping previous $name process, pid=$pid"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi

  rm -f "$pid_file"
}

start_process() {
  local name="$1"
  local workdir="$2"
  local logfile="$3"
  local command_string="$4"
  local pid_file="$RUN_DIR/$name.pid"

  stop_pid_process "$name"
  log "Starting $name"
  (
    cd "$workdir"
    exec bash -lc "$command_string"
  ) > "$logfile" 2>&1 &

  echo "$!" > "$pid_file"
  log "$name started, pid=$(cat "$pid_file"), log=$logfile"
}

start_realtime_backend() {
  local cmd
  cmd='set -a; [ -f .env ] && . ./.env; set +a; export LLM_PROVIDER="${LLM_PROVIDER:-gongan}"; export LISTEN_PORT="${LISTEN_PORT:-8010}"; export TTS_TYPE="${TTS_TYPE:-sparktts}"; export TTS_SERVER="${TTS_SERVER:-http://localhost:8779}"; exec .venv/bin/python app_v2.py --max_session 10 --tts "$TTS_TYPE" --TTS_SERVER "$TTS_SERVER" --wav2lip_size 256 --transport webrtc'
  start_process "digitalhuman-realtime" "$BACKEND_DIR" "$LOG_DIR/realtime.log" "$cmd"
}

start_device_service() {
  local cmd
  cmd='if [ -x .venv/bin/fastapi ]; then exec .venv/bin/fastapi run app/main.py --port '"$DEVICE_PORT"' --host '"$BIND_HOST"'; else exec uv run fastapi run app/main.py --port '"$DEVICE_PORT"' --host '"$BIND_HOST"'; fi'
  start_process "digitalhuman-device" "$DEVICE_DIR" "$LOG_DIR/device.log" "$cmd"
}

frontend_image_exists() {
  docker_cmd image inspect "$FRONTEND_IMAGE" >/dev/null 2>&1
}

prepare_frontend_image() {
  if [ "$PULL_FRONTEND_IMAGE" = "1" ]; then
    log "Pulling frontend image: $FRONTEND_IMAGE"
    docker_cmd pull "$FRONTEND_IMAGE"
    return 0
  fi

  if [ "$BUILD_FRONTEND_IMAGE" = "1" ]; then
    log "Building frontend image: $FRONTEND_IMAGE"
    docker_cmd build -t "$FRONTEND_IMAGE" "$FRONTEND_DIR"
    return 0
  fi

  if [ "$BUILD_FRONTEND_IMAGE" = "auto" ]; then
    if frontend_image_exists; then
      log "Frontend image already exists: $FRONTEND_IMAGE"
    else
      log "Frontend image is missing; building: $FRONTEND_IMAGE"
      docker_cmd build -t "$FRONTEND_IMAGE" "$FRONTEND_DIR"
    fi
    return 0
  fi

  frontend_image_exists || die "Frontend image $FRONTEND_IMAGE does not exist. Set BUILD_FRONTEND_IMAGE=1 or PULL_FRONTEND_IMAGE=1."
}

start_frontend_container() {
  prepare_frontend_image

  log "Starting frontend container: $FRONTEND_CONTAINER"
  docker_cmd rm -f "$FRONTEND_CONTAINER" >/dev/null 2>&1 || true
  docker_cmd run -d \
    --name "$FRONTEND_CONTAINER" \
    --restart unless-stopped \
    --add-host=host.docker.internal:host-gateway \
    -p "$HTTP_PORT:80" \
    -p "$HTTPS_PORT:443" \
    -e BACKEND_HOST="$BACKEND_HOST" \
    -v "$CERT_DIR:/certs:ro" \
    "$FRONTEND_IMAGE" >/dev/null

  log "frontend started, container=$FRONTEND_CONTAINER, backend=$BACKEND_HOST"
}

wait_http() {
  local name="$1"
  local url="$2"
  local allow_fail="${3:-0}"

  log "Waiting for $name: $url"
  local end=$((SECONDS + WAIT_SECONDS))
  while [ "$SECONDS" -lt "$end" ]; do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      printf '[OK] %s\n' "$url"
      return 0
    fi
    sleep 2
  done

  if [ "$allow_fail" = "1" ]; then
    warn "$name did not become ready within ${WAIT_SECONDS}s: $url"
    return 0
  fi

  die "$name did not become ready within ${WAIT_SECONDS}s: $url"
}

show_summary() {
  log "Service status"
  printf 'Realtime backend: %s\n' "$(cat "$RUN_DIR/digitalhuman-realtime.pid" 2>/dev/null || echo unknown)"
  printf 'Device service:    %s\n' "$(cat "$RUN_DIR/digitalhuman-device.pid" 2>/dev/null || echo unknown)"
  docker_cmd ps --filter "name=$FRONTEND_CONTAINER" --format 'Frontend:         {{.Names}} {{.Status}} {{.Ports}}' || true

  cat <<EOF

Logs:
  tail -f $LOG_DIR/realtime.log
  tail -f $LOG_DIR/device.log
  docker logs -f $FRONTEND_CONTAINER

Local checks:
  curl http://127.0.0.1:$REALTIME_PORT/ready
  curl http://127.0.0.1:$DEVICE_PORT/ready
  curl http://127.0.0.1:$HTTP_PORT/backend/ready
  curl http://127.0.0.1:$HTTP_PORT/api/ready
EOF
}

main() {
  prepare_dirs
  load_backend_env
  preflight
  start_realtime_backend
  start_device_service
  start_frontend_container

  wait_http "realtime backend" "http://127.0.0.1:$REALTIME_PORT/ready"
  wait_http "device service" "http://127.0.0.1:$DEVICE_PORT/ready"
  wait_http "frontend" "http://127.0.0.1:$HTTP_PORT/"
  wait_http "frontend backend proxy" "http://127.0.0.1:$HTTP_PORT/backend/ready" 1
  wait_http "frontend device proxy" "http://127.0.0.1:$HTTP_PORT/api/ready" 1
  show_summary
}

main "$@"
