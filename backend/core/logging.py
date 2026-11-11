"""Centralised logging configuration.

Every module should use ``logging.getLogger(__name__)``; this module only
configures the root logger once at application startup.
"""

from __future__ import annotations

import logging
import sys

from backend.core.config import get_settings


def configure_logging() -> None:
    """Configure the root logger. Call once from ``backend.main``."""
    settings = get_settings()

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper so callers don't need to import ``logging``."""
    return logging.getLogger(name)