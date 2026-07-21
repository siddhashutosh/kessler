"""Structured logging: console + rotating file, request-id aware (NFR-2)."""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | rid=%(request_id)s | %(message)s"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_kessler_configured", False):
        return

    root.setLevel(level)
    fmt = logging.Formatter(_FORMAT)
    rid_filter = RequestIdFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    console.addFilter(rid_filter)
    root.addHandler(console)

    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_dir / "kessler.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        file_handler.addFilter(rid_filter)
        root.addHandler(file_handler)
    except OSError as exc:  # file logging is best-effort; console always works
        root.warning("File logging disabled: %s", exc)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    root._kessler_configured = True  # type: ignore[attr-defined]
