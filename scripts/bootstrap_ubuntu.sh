#!/usr/bin/env bash
set -Eeuo pipefail

# Prepare a fresh Ubuntu host for digitalhuman-XunFei.
# This script installs system dependencies, clones/updates the project,
# installs Python dependencies, creates runtime directories, prepares TLS
# certificates for the frontend container, and places the three required
# large runtime assets.
#
# It does not start services. Use the separate service-start script after this
# script finishes and after you fill realtime-digital-human/.env.

PROJECT_ROOT="${PROJECT_ROOT:-/opt/digitalhuman}"
SRC_DIR="${SRC_DIR:-$PROJECT_ROOT/src}"
REPO_URL="${REPO_URL:-https://github.com/eiffelmen/digitalhuman-XunFei.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
CERT_DIR="${CERT_DIR:-/data/prod/fe/certs}"
ASSET_CACHE_DIR="${ASSET_CACHE_DIR:-$PROJECT_ROOT/assets-cache}"
ASSET_SOURCE_DIR="${ASSET_SOURCE_DIR:-}"
ASSET_BASE_URL="${ASSET_BASE_URL:-}"

INSTALL_SYSTEM_PACKAGES="${INSTALL_SYSTEM_PACKAGES:-1}"
INSTALL_PYTHON_DEPS="${INSTALL_PYTHON_DEPS:-1}"
SKIP_ASSETS="${SKIP_ASSETS:-0}"

VIDEO_FILE="反诈视频.mp4"
WAV2LIP_FILE="wav2lip.pth"
DATA_ZIP_FILE="data.zip"

VIDEO_SHARE_URL="https://pan.baidu.com/s/1VleBdTUAKjl6COVOFHbctA?pwd=8y9j"
VIDEO_SHARE_PWD="8y9j"
WAV2LIP_SHARE_URL="https://pan.baidu.com/s/1Sm5NpQOa9Ue_No4gm_pVeA?pwd=pfq1"
WAV2LIP_SHARE_PWD="pfq1"
DATA_SHARE_URL="https://pan.baidu.com/s/1FtGG3WoNOXHZdwBWKc-yJw?pwd=fhnq"
DATA_SHARE_PWD="fhnq"

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

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

ensure_command() {
  command -v "$1" >/dev/null 2>&1
}

install_system_packages() {
  [ "$INSTALL_SYSTEM_PACKAGES" = "1" ] || return 0

  log "Installing Ubuntu system packages"
  as_root apt-get update
  as_root DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    wget \
    git \
    unzip \
    ffmpeg \
    build-essential \
    make \
    cmake \
    pkg-config \
    python3 \
    python3-venv \
    python3-pip \
    openssl \
    software-properties-common \
    lsb-release \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    docker.io

  as_root apt-get install -y docker-compose-plugin || warn "docker-compose-plugin is unavailable from current apt sources; continuing with docker.io."
  as_root systemctl enable --now docker

  if [ "$(id -u)" -ne 0 ]; then
    as_root usermod -aG docker "$USER" || true
  fi
}

install_uv() {
  if ensure_command uv; then
    log "uv already installed: $(uv --version)"
    return 0
  fi

  log "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  ensure_command uv || die "uv installation finished but uv is not in PATH. Reopen shell or export PATH=\"\$HOME/.local/bin:\$PATH\"."
}

check_gpu_hint() {
  if lspci 2>/dev/null | grep -qi nvidia; then
    if ensure_command nvidia-smi; then
      log "NVIDIA GPU detected"
      nvidia-smi || true
    else
      warn "NVIDIA GPU detected, but nvidia-smi is missing. Install NVIDIA driver and reboot before running GPU inference."
    fi
  else
    warn "No NVIDIA GPU was detected by lspci. The realtime backend may run very slowly or fail if GPU is required."
  fi
}

git_args=()
prepare_git_auth() {
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    git_args=(-c "http.https://github.com/.extraheader=Authorization: Bearer ${GITHUB_TOKEN}")
  fi
}

clone_or_update_repo() {
  log "Preparing project source at $SRC_DIR"
  as_root mkdir -p "$PROJECT_ROOT"
  as_root chown -R "$(id -u):$(id -g)" "$PROJECT_ROOT"

  prepare_git_auth
  if [ -d "$SRC_DIR/.git" ]; then
    git "${git_args[@]}" -C "$SRC_DIR" fetch origin "$REPO_BRANCH"
    git -C "$SRC_DIR" checkout "$REPO_BRANCH"
    git "${git_args[@]}" -C "$SRC_DIR" pull --ff-only origin "$REPO_BRANCH"
  else
    git "${git_args[@]}" clone --branch "$REPO_BRANCH" "$REPO_URL" "$SRC_DIR"
  fi
}

link_component() {
  local target="$1"
  local link="$2"

  if [ -L "$link" ]; then
    ln -sfn "$target" "$link"
  elif [ -e "$link" ]; then
    warn "$link already exists and is not a symlink; leaving it unchanged."
  else
    ln -s "$target" "$link"
  fi
}

prepare_project_layout() {
  log "Preparing /opt/digitalhuman compatible layout"
  link_component "$SRC_DIR/realtime-digital-human" "$PROJECT_ROOT/be"
  link_component "$SRC_DIR/device" "$PROJECT_ROOT/device"
  link_component "$SRC_DIR/zkxh-digitalhuman-front" "$PROJECT_ROOT/fe"

  mkdir -p \
    "$PROJECT_ROOT/device/resources" \
    "$PROJECT_ROOT/be/wav2lip256" \
    "$PROJECT_ROOT/be/data" \
    "$ASSET_CACHE_DIR"

  if [ ! -f "$PROJECT_ROOT/be/.env" ] && [ -f "$PROJECT_ROOT/be/.env.template" ]; then
    cp "$PROJECT_ROOT/be/.env.template" "$PROJECT_ROOT/be/.env"
    warn "Created $PROJECT_ROOT/be/.env from template. Fill real API keys before starting backend services."
  fi
}

install_python_dependencies() {
  [ "$INSTALL_PYTHON_DEPS" = "1" ] || return 0

  log "Installing Python 3.12 with uv if needed"
  uv python install 3.12

  log "Installing realtime backend Python dependencies"
  (cd "$PROJECT_ROOT/be" && uv sync --locked)

  log "Installing device service Python dependencies"
  (cd "$PROJECT_ROOT/device" && uv sync --locked)
}

prepare_frontend_certs() {
  log "Preparing frontend TLS certificate files"
  as_root mkdir -p "$CERT_DIR"
  if [ ! -f "$CERT_DIR/service.pem" ] || [ ! -f "$CERT_DIR/service-key.pem" ]; then
    local cn
    cn="$(hostname -I 2>/dev/null | awk '{print $1}')"
    cn="${cn:-digitalhuman.local}"
    as_root openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
      -keyout "$CERT_DIR/service-key.pem" \
      -out "$CERT_DIR/service.pem" \
      -subj "/CN=$cn"
    as_root chmod 644 "$CERT_DIR/service.pem"
    as_root chmod 600 "$CERT_DIR/service-key.pem"
  fi
}

find_cached_asset() {
  local filename="$1"

  if [ -n "$ASSET_SOURCE_DIR" ] && [ -f "$ASSET_SOURCE_DIR/$filename" ]; then
    printf '%s\n' "$ASSET_SOURCE_DIR/$filename"
    return 0
  fi

  if [ -f "$ASSET_CACHE_DIR/$filename" ]; then
    printf '%s\n' "$ASSET_CACHE_DIR/$filename"
    return 0
  fi

  find "$ASSET_CACHE_DIR" -type f -name "$filename" -print -quit 2>/dev/null
}

download_direct_asset() {
  local filename="$1"
  local url="$2"

  [ -n "$url" ] || return 1
  log "Downloading $filename from direct URL"
  curl -fL --retry 5 --retry-delay 3 -C - -o "$ASSET_CACHE_DIR/$filename" "$url"
}

download_from_baidupcs() {
  local filename="$1"
  local share_url="$2"
  local share_pwd="$3"

  if ! ensure_command BaiduPCS-Go; then
    return 1
  fi

  log "Trying BaiduPCS-Go download for $filename"
  BaiduPCS-Go config set -savedir "$ASSET_CACHE_DIR" >/dev/null || true
  BaiduPCS-Go transfer --download "$share_url" "$share_pwd" || return 1
  [ -n "$(find_cached_asset "$filename")" ]
}

resolve_asset() {
  local filename="$1"
  local direct_url="$2"
  local share_url="$3"
  local share_pwd="$4"
  local found

  found="$(find_cached_asset "$filename" || true)"
  if [ -n "$found" ]; then
    printf '%s\n' "$found"
    return 0
  fi

  if download_direct_asset "$filename" "$direct_url"; then
    found="$(find_cached_asset "$filename" || true)"
    [ -n "$found" ] && printf '%s\n' "$found" && return 0
  fi

  if download_from_baidupcs "$filename" "$share_url" "$share_pwd"; then
    found="$(find_cached_asset "$filename" || true)"
    [ -n "$found" ] && printf '%s\n' "$found" && return 0
  fi

  die "Cannot obtain $filename. Put it under ASSET_SOURCE_DIR, provide VIDEO_URL/WAV2LIP_URL/DATA_ZIP_URL or ASSET_BASE_URL, or install and log in to BaiduPCS-Go."
}

normalize_data_dir() {
  local expected="$PROJECT_ROOT/be/data/avatars/wav2lip_avatar11/coords.pkl"
  local coords
  [ -f "$expected" ] && return 0

  coords="$(find "$PROJECT_ROOT/be/data" -path "*/avatars/wav2lip_avatar11/coords.pkl" -print -quit 2>/dev/null || true)"
  [ -n "$coords" ] || return 0

  local avatars_dir
  avatars_dir="$(dirname "$(dirname "$coords")")"
  if [ "$avatars_dir" != "$PROJECT_ROOT/be/data/avatars" ]; then
    rm -rf "$PROJECT_ROOT/be/data/avatars"
    mv "$avatars_dir" "$PROJECT_ROOT/be/data/avatars"
  fi
}

place_assets() {
  [ "$SKIP_ASSETS" = "0" ] || {
    warn "SKIP_ASSETS=1, skipping large runtime asset placement."
    return 0
  }

  local video_url="${VIDEO_URL:-}"
  local wav2lip_url="${WAV2LIP_URL:-}"
  local data_zip_url="${DATA_ZIP_URL:-}"

  if [ -n "$ASSET_BASE_URL" ]; then
    video_url="${video_url:-$ASSET_BASE_URL/$VIDEO_FILE}"
    wav2lip_url="${wav2lip_url:-$ASSET_BASE_URL/$WAV2LIP_FILE}"
    data_zip_url="${data_zip_url:-$ASSET_BASE_URL/$DATA_ZIP_FILE}"
  fi

  log "Preparing required large runtime assets"
  local video_path wav2lip_path data_zip_path
  video_path="$(resolve_asset "$VIDEO_FILE" "$video_url" "$VIDEO_SHARE_URL" "$VIDEO_SHARE_PWD")"
  wav2lip_path="$(resolve_asset "$WAV2LIP_FILE" "$wav2lip_url" "$WAV2LIP_SHARE_URL" "$WAV2LIP_SHARE_PWD")"
  data_zip_path="$(resolve_asset "$DATA_ZIP_FILE" "$data_zip_url" "$DATA_SHARE_URL" "$DATA_SHARE_PWD")"

  install -m 0644 "$video_path" "$PROJECT_ROOT/device/resources/$VIDEO_FILE"
  install -m 0644 "$wav2lip_path" "$PROJECT_ROOT/be/wav2lip256/$WAV2LIP_FILE"
  unzip -oq "$data_zip_path" -d "$PROJECT_ROOT/be/data"
  normalize_data_dir
}

verify_result() {
  log "Verifying installation"
  local missing=0
  local checks=(
    "$PROJECT_ROOT/src/README.md"
    "$PROJECT_ROOT/be/.venv"
    "$PROJECT_ROOT/device/.venv"
    "$PROJECT_ROOT/device/resources/$VIDEO_FILE"
    "$PROJECT_ROOT/be/wav2lip256/$WAV2LIP_FILE"
    "$PROJECT_ROOT/be/data/avatars/wav2lip_avatar11/coords.pkl"
    "$CERT_DIR/service.pem"
    "$CERT_DIR/service-key.pem"
  )

  for path in "${checks[@]}"; do
    if [ -e "$path" ]; then
      printf '[OK] %s\n' "$path"
    else
      printf '[MISSING] %s\n' "$path"
      missing=1
    fi
  done

  if [ "$missing" -ne 0 ]; then
    die "Bootstrap finished with missing files. Fix the missing items before starting services."
  fi

  log "Bootstrap finished. Next: fill $PROJECT_ROOT/be/.env, then run your service-start script."
  if [ "$(id -u)" -ne 0 ]; then
    warn "If this user was just added to docker group, log out and log in again before running docker without sudo."
  fi
}

main() {
  install_system_packages
  install_uv
  check_gpu_hint
  clone_or_update_repo
  prepare_project_layout
  install_python_dependencies
  prepare_frontend_certs
  place_assets
  verify_result
}

main "$@"
