import os
import sys

from loguru import logger


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _pipeline_diag_filter(record) -> bool:
    message = record["message"]
    markers = (
        "[PERF]",
        "[时间点]",
        "[AUDIO_DIAG]",
        "[SYNC_DIAG]",
        "[PIPELINE]",
        "[ASR]",
        "[CLIENT_METRICS]",
        "audio_ws_",
        "audio_stream",
        "audio_recorder",
        "audio_chunk_",
        "VAD:",
        "GonganTTS",
        "Gongan LLM",
        "queue dropped",
        "track_recv",
        "speaking_state_change",
    )
    return any(marker in message for marker in markers)


os.makedirs("./logs", exist_ok=True)

logger.remove()
logger.add(sys.stderr, level="DEBUG")
logger.add("./logs/file_{time}.log", rotation="1 week", retention="14 days")

if _env_bool("PIPELINE_DIAG_LOG_ENABLED", True):
    pipeline_log_path = os.environ.get(
        "PIPELINE_DIAG_LOG_PATH",
        "./logs/pipeline_diagnostics.log",
    )
    logger.add(
        pipeline_log_path,
        level=os.environ.get("PIPELINE_DIAG_LOG_LEVEL", "DEBUG"),
        rotation=os.environ.get("PIPELINE_DIAG_LOG_ROTATION", "200 MB"),
        retention=os.environ.get("PIPELINE_DIAG_LOG_RETENTION", "7 days"),
        filter=_pipeline_diag_filter,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
