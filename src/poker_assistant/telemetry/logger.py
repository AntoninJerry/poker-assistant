"""Structured logging utilities."""

import logging

from ..config import AppSettings

_LOGGER: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    config = AppSettings()
    level = logging.INFO  # Default level for now

    logger = logging.getLogger("poker_assistant")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)

    _LOGGER = logger
    return logger
