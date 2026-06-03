#!/bin/bash

set -e

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

export LLM_PROVIDER=${LLM_PROVIDER:-iflytek}
export LISTEN_PORT=${LISTEN_PORT:-8010}
export TTS_TYPE=${TTS_TYPE:-iflytts}
export TTS_SERVER=${TTS_SERVER:-http://localhost:8779}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export WAV2LIP_BACKEND=${WAV2LIP_BACKEND:-pytorch}
export WAV2LIP_ENGINE_PATH=${WAV2LIP_ENGINE_PATH:-./wav2lip256/wav2lip_fp16.engine}

.venv/bin/python app_v2.py \
    --max_session 10 \
    --tts "$TTS_TYPE" \
    --TTS_SERVER "$TTS_SERVER" \
    --wav2lip_size 256 \
    --wav2lip_backend "$WAV2LIP_BACKEND" \
    --wav2lip_engine_path "$WAV2LIP_ENGINE_PATH" \
    --transport webrtc
