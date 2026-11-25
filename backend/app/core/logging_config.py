"""One rotating log file for the whole API.

Everything the server writes (uvicorn, application loggers, background jobs) goes
to logs/edusense.log, capped and rotated, so a long-running classroom session
cannot fill the disk and one file is enough to diagnose a failure.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import warnings
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FILE = LOG_DIR / "edusense.log"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUPS = 5

# Third-party noise seen in this project: lz4 frame errors from ChromaDB,
# ProactorBasePipe connection resets from the asyncio loops on Windows, and
# TensorFlow/DeepFace chatter from the retired server-side detector.
_QUIET_LOGGERS = {
    "lz4": logging.ERROR,
    "lz4.frame": logging.ERROR,
    "chromadb.telemetry": logging.WARNING,
    "chromadb.telemetry.product.posthog": logging.ERROR,
    "asyncio": logging.WARNING,
    "tensorflow": logging.ERROR,
    "deepface": logging.ERROR,
    "urllib3": logging.WARNING,
    "httpx": logging.WARNING,
    "PIL": logging.WARNING,
    "matplotlib": logging.ERROR,
    "apscheduler.executors.default": logging.WARNING,
}

_CONFIGURED = False


def configure_logging(level: str | None = None) -> None:
    """Idempotent: call once per process before the app starts."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_level = (level or os.environ.get("EDUSENSE_LOG_LEVEL") or "INFO").upper()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(log_level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.setLevel(log_level)

    root = logging.getLogger()
    root.setLevel(log_level)
    # Avoid duplicate handlers when uvicorn imports the app twice (workers).
    for handler in list(root.handlers):
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            root.removeHandler(handler)
    root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        root.addHandler(console)

    for name, quiet_level in _QUIET_LOGGERS.items():
        logging.getLogger(name).setLevel(max(quiet_level, logging.getLogger(name).level))

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    # Windows asyncio logs "ConnectionResetError: [WinError 10054]" and
    # "ProactorBasePipeTransport.__del__ called after close" on every browser
    # tab close; they are noise, not server faults.
    warnings.filterwarnings("ignore", message=r".*ProactorBasePipeTransport.*")
    warnings.filterwarnings("ignore", message=r".*unclosed transport.*")

    # The running loop's handler is installed in app.main.startup(), where a
    # loop actually exists; doing it here created an unused loop and warned.
    _CONFIGURED = True
