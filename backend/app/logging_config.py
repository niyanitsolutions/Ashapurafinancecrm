"""Structured logging to backend/logs/*.log (rotating), not just stdout — set up once at
process start for both the API (main.py) and the worker (worker/worker_settings.py).
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def _rotating_handler(filename: str, level: int) -> logging.Handler:
    LOG_DIR.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    return handler


def configure_logging(*, process: str = "app") -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    root.addHandler(_rotating_handler("application.log", logging.INFO))
    root.addHandler(_rotating_handler("error.log", logging.ERROR))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    if process == "worker":
        worker_logger = logging.getLogger("afs.worker")
        worker_logger.addHandler(_rotating_handler("worker.log", logging.INFO))
    else:
        access_logger = logging.getLogger("afs.access")
        access_logger.addHandler(_rotating_handler("access.log", logging.INFO))
