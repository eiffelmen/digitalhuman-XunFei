#!/bin/bash

export LLM_PROVIDER=${LLM_PROVIDER:-gongan}
export LISTEN_PORT=${LISTEN_PORT:-8010}
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-1}

exec .venv/bin/python app_v2.py --max_session 10 --tts sparktts --TTS_SERVER http://localhost:8779 --wav2lip_size 256 --transport webrtc
