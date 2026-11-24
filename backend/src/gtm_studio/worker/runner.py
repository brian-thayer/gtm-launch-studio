"""Worker entry point. A placeholder until the job queue exists (S33)."""

import time
from collections.abc import Callable

import structlog

log = structlog.get_logger()

IDLE_INTERVAL_SECONDS = 30.0


def run_idle(
    *,
    once: bool = False,
    interval: float = IDLE_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Log an idle heartbeat. With ``once`` it logs a single time and returns."""
    while True:
        log.info("worker idle (implemented in S33)")
        if once:
            return
        sleep(interval)
