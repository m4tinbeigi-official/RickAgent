"""
Logging — consistent format across all modules.
Writes to stdout AND to logs/app.log (rotating, max 5 MB × 3 backups).
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

_LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "logs")
)
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_FMT = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Create the logs/ directory on first import
os.makedirs(_LOG_DIR, exist_ok=True)

# Module-level rotating file handler — shared across all loggers
_file_handler: logging.Handler | None = None


def _get_file_handler() -> logging.Handler:
    global _file_handler
    if _file_handler is None:
        _file_handler = logging.handlers.RotatingFileHandler(
            _LOG_FILE,
            maxBytes=5 * 1024 * 1024,   # 5 MB per file
            backupCount=3,
            encoding="utf-8",
        )
        _file_handler.setFormatter(_FMT)
    return _file_handler


def setup_logger(name: str) -> logging.Logger:
    """
    Return a logger with consistent format.
    Logs go to both stdout and logs/app.log (rotating).
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        # Console handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(_FMT)
        logger.addHandler(console)

        # Rotating file handler
        try:
            logger.addHandler(_get_file_handler())
        except OSError:
            pass   # If we can't write the log file, just use stdout

    if not logger.level:
        logger.setLevel(logging.INFO)

    return logger
