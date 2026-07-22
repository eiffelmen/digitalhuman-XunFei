# 讯飞 LLM 凭据
if (-not $env:IFLYTEK_APPID) { $env:IFLYTEK_APPID = "" }
if (-not $env:IFLYTEK_API_KEY) { $env:IFLYTEK_API_KEY = "" }
if (-not $env:IFLYTEK_API_SECRET) { $env:IFLYTEK_API_SECRET = "" }

# 讯飞 TTS 凭据（AIUI appid/api_key，通常与 LLM 相同）
if (-not $env:IFLY_APP_ID) { $env:IFLY_APP_ID = $env:IFLYTEK_APPID }
if (-not $env:IFLY_API_KEY) { $env:IFLY_API_KEY = $env:IFLYTEK_API_KEY }

if (-not $env:LLM_PROVIDER) { $env:LLM_PROVIDER = "gongan" }
if (-not $env:TTS_PROVIDER) { $env:TTS_PROVIDER = "gongantts" }
if (-not $env:LISTEN_PORT) { $env:LISTEN_PORT = "8010" }
if (-not $env:CUDA_VISIBLE_DEVICES) { $env:CUDA_VISIBLE_DEVICES = "1" }

& uv run --no-sync python app_v2.py `
  --max_session 10 `
  --avatar_id wav2lip_avatar11 `
  --tts "$env:TTS_PROVIDER" `
  --wav2lip_size 256 `
  --transport webrtc
