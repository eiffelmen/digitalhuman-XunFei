@echo off

cd /d "%~dp0"

REM Parse .env file if it exists
if exist .env (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        set "%%A=%%B"
    )
)

REM Set default environment variables if not overridden by .env
if "%LLM_PROVIDER%"=="" set "LLM_PROVIDER=iflytek"
if "%LISTEN_PORT%"=="" set "LISTEN_PORT=8010"
if "%TTS_TYPE%"=="" set "TTS_TYPE=iflytts"
if "%TTS_SERVER%"=="" set "TTS_SERVER=http://localhost:8779"
if "%CUDA_VISIBLE_DEVICES%"=="" set "CUDA_VISIBLE_DEVICES=0"

REM Check for python executable in virtual environment
if exist .venv\Scripts\python.exe (
    set "PYTHON_EXEC=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXEC=python"
    echo [WARN] Could not find .venv\Scripts\python.exe, using system default python.
)

REM Start the server
echo [INFO] Starting DigitalMan Server...
echo [INFO] LLM_PROVIDER=%LLM_PROVIDER%, PORT=%LISTEN_PORT%, TTS=%TTS_TYPE%
"%PYTHON_EXEC%" app_v2.py --max_session 10 --tts "%TTS_TYPE%" --TTS_SERVER "%TTS_SERVER%" --wav2lip_size 256 --transport webrtc
