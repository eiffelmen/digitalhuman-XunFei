#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ONNX_PATH="${ONNX_PATH:-./wav2lip256/wav2lip_256.onnx}"
ENGINE_PATH="${ENGINE_PATH:-./wav2lip256/wav2lip_fp16.engine}"
MODEL_SIZE="${MODEL_SIZE:-256}"
MIN_BATCH="${MIN_BATCH:-1}"
OPT_BATCH="${OPT_BATCH:-16}"
MAX_BATCH="${MAX_BATCH:-16}"
WORKSPACE_MIB="${WORKSPACE_MIB:-2048}"
PRECISION="${PRECISION:-fp16}"

if ! command -v trtexec >/dev/null 2>&1; then
    echo "[ERROR] trtexec not found. Install TensorRT on the Ubuntu GPU server first." >&2
    exit 1
fi

if [ ! -f "$ONNX_PATH" ]; then
    echo "[ERROR] ONNX file not found: $ONNX_PATH" >&2
    echo "Run: python scripts/export_wav2lip_onnx.py --output $ONNX_PATH" >&2
    exit 1
fi

mkdir -p "$(dirname "$ENGINE_PATH")"

PRECISION_ARGS=()
if [ "$PRECISION" = "fp16" ]; then
    PRECISION_ARGS+=(--fp16)
elif [ "$PRECISION" != "fp32" ]; then
    echo "[ERROR] PRECISION must be fp16 or fp32, got: $PRECISION" >&2
    exit 1
fi

echo ">>> Building TensorRT engine"
echo "ONNX:   $ONNX_PATH"
echo "Engine: $ENGINE_PATH"
echo "Shapes: min=$MIN_BATCH opt=$OPT_BATCH max=$MAX_BATCH model_size=$MODEL_SIZE"

trtexec \
    --onnx="$ONNX_PATH" \
    --saveEngine="$ENGINE_PATH" \
    "${PRECISION_ARGS[@]}" \
    --minShapes=mel:${MIN_BATCH}x1x80x16,face:${MIN_BATCH}x6x${MODEL_SIZE}x${MODEL_SIZE} \
    --optShapes=mel:${OPT_BATCH}x1x80x16,face:${OPT_BATCH}x6x${MODEL_SIZE}x${MODEL_SIZE} \
    --maxShapes=mel:${MAX_BATCH}x1x80x16,face:${MAX_BATCH}x6x${MODEL_SIZE}x${MODEL_SIZE} \
    --memPoolSize=workspace:${WORKSPACE_MIB}

echo
echo ">>> TensorRT engine created: $ENGINE_PATH"
echo "Add these lines to realtime-digital-human/.env on the server:"
echo "WAV2LIP_BACKEND=tensorrt"
echo "WAV2LIP_ENGINE_PATH=$ENGINE_PATH"
