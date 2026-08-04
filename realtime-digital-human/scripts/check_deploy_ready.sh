#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
fi

fail() {
    echo "[FAIL] $*" >&2
    exit 1
}

warn() {
    echo "[WARN] $*" >&2
}

ok() {
    echo "[OK] $*"
}

command -v uv >/dev/null 2>&1 || fail "uv is not installed. Install uv first."
ok "uv found: $(command -v uv)"

[ -f "./wav2lip256/wav2lip.pth" ] || fail "missing ./wav2lip256/wav2lip.pth"
ok "wav2lip checkpoint exists"

[ -d "./data" ] || fail "missing ./data directory. Restore data.zip first."
ok "data directory exists"

uv run --no-sync python - <<'PY'
import sys

try:
    import torch
except Exception as exc:
    print(f"[FAIL] torch import failed: {exc}", file=sys.stderr)
    print("Run: uv sync", file=sys.stderr)
    raise SystemExit(1)

print(f"[OK] torch={torch.__version__} cuda_available={torch.cuda.is_available()}")
if not torch.cuda.is_available():
    print("[WARN] CUDA is not available to torch.", file=sys.stderr)
PY

backend="${WAV2LIP_BACKEND:-pytorch}"
if [ "$backend" = "tensorrt" ] || [ "$backend" = "trt" ]; then
    engine_path="${WAV2LIP_ENGINE_PATH:-./wav2lip256/wav2lip_server_fp16.engine}"
    [ -f "$engine_path" ] || fail "TensorRT engine not found: $engine_path"
    ok "TensorRT engine exists: $engine_path"

    uv run --no-sync python - <<'PY'
import sys

try:
    import tensorrt as trt
except Exception as exc:
    print(f"[FAIL] tensorrt import failed: {exc}", file=sys.stderr)
    print("Run: uv pip install tensorrt-cu12", file=sys.stderr)
    raise SystemExit(1)

print(f"[OK] tensorrt={trt.__version__}")
PY
else
    ok "WAV2LIP_BACKEND=$backend"
fi

ok "deployment preflight passed"
