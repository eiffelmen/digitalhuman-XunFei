#!/bin/bash

# docker 部署
# 从环境变量获取配置参数，如果未设置则使用默认值
TTS_TYPE=${TTS_TYPE:-flashtts}
AVATAR_ID=${AVATAR_ID:-wav2lip_avatar5}

CUDA_VISIBLE_DEVICES=1 uv run python app_v2.py --max_session 10 --tts ${TTS_TYPE} --avatar_id ${AVATAR_ID} --TTS_SERVER ${TTS_SERVICE} --wav2lip_size 256 --transport webrtc

