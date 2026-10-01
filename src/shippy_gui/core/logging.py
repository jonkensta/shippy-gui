"""Logging configuration utilities."""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

import ibp_printing

from shippy_gui.core.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES


def configure_logging(log_path: str) -> Path:
    """Configure application logging to a rotating file.

    Also enables ibp-printing's verbose printer logs (``printer.log`` and
    ``printer.jsonl`` in its per-machine log directory). Printer records still
    propagate to the app log at INFO and above.

    Returns:
        The directory ibp-printing writes its printer logs to.
    """
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    handler = RotatingFileHandler(
        log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
    )
    # ibp-printing logs at DEBUG; keep that detail in its own files only.
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    # The GUI has no console (pythonw); everything goes to the log files.
    return ibp_printing.configure_logging(console=False)
