"""Logging configuration utilities."""

import logging
from logging.handlers import RotatingFileHandler
import os

from shippy_gui.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


def configure_logging(log_path: str) -> None:
    """Configure application logging to a rotating file."""
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
    )
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
