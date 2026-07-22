#!/bin/bash

# 讯飞 LLM 凭据
export IFLYTEK_APPID=${IFLYTEK_APPID:-""}
export IFLYTEK_API_KEY=${IFLYTEK_API_KEY:-""}
export IFLYTEK_API_SECRET=${IFLYTEK_API_SECRET:-""}

# 讯飞 TTS 凭据（AIUI appid/api_key，通常与 LLM 相同）
export IFLY_APP_ID=${IFLY_APP_ID:-${IFLYTEK_APPID}}
export IFLY_API_KEY=${IFLY_API_KEY:-${IFLYTEK_API_KEY}}

export LLM_PROVIDER=${LLM_PROVIDER:-gongan}
export TTS_PROVIDER=${TTS_PROVIDER:-gongantts}
export LISTEN_PORT=${LISTEN_PORT:-8010}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-1}

UV_RUN_ARGS=()
if [ "${UV_NO_SYNC:-0}" = "1" ]; then
  UV_RUN_ARGS+=(--no-sync)
fi

exec uv run "${UV_RUN_ARGS[@]}" python app_v2.py \
  --max_session 10 \
  --avatar_id wav2lip_avatar11 \
  --batch_size "${DIGITAL_HUMAN_BATCH_SIZE:-4}" \
  --tts "$TTS_PROVIDER" \
  --wav2lip_size 256 \
  --transport webrtc
