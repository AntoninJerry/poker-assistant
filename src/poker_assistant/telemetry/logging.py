"""Structured logging utilities."""

import logging

from ..config import AppConfig, load_config

_LOGGER: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    config: AppConfig = load_config()
    level = getattr(logging, config.logging.level, logging.INFO)

    logger = logging.getLogger("poker_assistant")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)

    _LOGGER = logger
    return logger
