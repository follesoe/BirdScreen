"""Central logging for BirdScreen.

Library modules use ``logging.getLogger(__name__)`` and never print diagnostics
directly, so output can be routed to the console (CLIs) or captured for the web
UI. Pure *data* output (a prompt, JSON, a model list) still goes to stdout.
"""

from __future__ import annotations

import logging
from collections import deque

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%H:%M:%S"
_ROOT = "birdscreen"


class RingBufferHandler(logging.Handler):
    """Keep the most recent N formatted records in memory for the web UI."""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self.records: deque[str] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))

    def recent(self) -> list[str]:
        return list(self.records)


_buffer = RingBufferHandler()
_buffer.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))


def setup_logging(level: int = logging.INFO, *, console: bool = True) -> None:
    """Configure the ``birdscreen`` logger (idempotent)."""
    logger = logging.getLogger(_ROOT)
    logger.setLevel(level)
    logger.handlers.clear()
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _DATE_FORMAT))
        logger.addHandler(console_handler)
    logger.addHandler(_buffer)
    logger.propagate = False


def recent_logs() -> list[str]:
    """Recent formatted log lines (oldest first) for the web UI."""
    return _buffer.recent()
