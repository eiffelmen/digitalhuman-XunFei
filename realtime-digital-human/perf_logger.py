import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

from mylogger import logger


PERF_ENABLED = os.environ.get("PERF_LOG_ENABLED", "1").lower() not in {
    "0",
    "false",
    "no",
}


def now() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def wall_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _format_value(value: Any) -> str:
    text = str(value)
    return text.replace("\n", "\\n").replace("\r", "\\r").replace(" ", "_")


def log_perf(module: str, action: str, duration_ms: Optional[float] = None, **fields):
    if not PERF_ENABLED:
        return

    parts = [f"[PERF] module={module}", f"action={action}"]
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.2f}")

    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_format_value(value)}")

    logger.info(" ".join(parts))


def log_timepoint(module: str, event: str, **fields):
    if not PERF_ENABLED:
        return

    parts = ["[时间点]", f"模块={module}", f"事件={event}", f"时间={wall_time()}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_format_value(value)}")

    logger.info(" ".join(parts))


@contextmanager
def perf_timer(module: str, action: str, **fields):
    start = now()
    try:
        yield
    finally:
        log_perf(module, action, elapsed_ms(start), **fields)
