#!/bin/bash

export LLM_PROVIDER=${LLM_PROVIDER:-gongan}
export LISTEN_PORT=${LISTEN_PORT:-8010}
export TTS_TYPE=${TTS_TYPE:-sparktts}
export TTS_SERVER=${TTS_SERVER:-http://localhost:8779}
# export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-1}

.venv/bin/python app_v2.py --max_session 10 --tts "$TTS_TYPE" --TTS_SERVER "$TTS_SERVER" --wav2lip_size 256 --transport webrtc
