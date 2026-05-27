import os
import time
from contextlib import contextmanager
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


@contextmanager
def perf_timer(module: str, action: str, **fields):
    start = now()
    try:
        yield
    finally:
        log_perf(module, action, elapsed_ms(start), **fields)
