"""Entry point for shippy-gui application."""

import logging
import os
import sys

from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.config import (
    get_font_size_from_path,
    resolve_config_paths,
    load_config,
)
from shippy_gui.core.constants import DEFAULT_LOG_FILENAME
from shippy_gui.core.logging import configure_logging
from shippy_gui.core.font import apply_font_size
from shippy_gui.main_window import MainWindow


def main():
    """Launch the shippy-gui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Shippy GUI")
    app.setOrganizationName("Inside Books Project")

    config_paths = resolve_config_paths()

    _configure_app_logging(config_paths.config_path, config_paths.active_load_path)

    # Apply configured font size
    font_size = get_font_size_from_path(config_paths.active_load_path)
    apply_font_size(app, font_size)

    # Note: We pass the intended config_path to MainWindow so that when the user
    # saves settings, they are written to config.ini, not config.example.ini.
    window = MainWindow(config_path=config_paths.config_path)
    window.show()

    sys.exit(app.exec())


def _configure_app_logging(config_path: str, load_path: str) -> None:
    """Configure logging using config settings."""
    config_dir = os.path.dirname(config_path)
    default_log_path = os.path.join(config_dir, DEFAULT_LOG_FILENAME)

    log_path = default_log_path
    try:
        config = load_config(load_path)
        log_setting = config.get_log_file(DEFAULT_LOG_FILENAME)
        if os.path.isabs(log_setting):
            log_path = log_setting
        else:
            log_path = os.path.join(config_dir, log_setting or DEFAULT_LOG_FILENAME)
    except Exception:  # pylint: disable=broad-exception-caught
        log_path = default_log_path

    configure_logging(log_path)
    logging.getLogger(__name__).info("Shippy GUI started")


if __name__ == "__main__":
    main()
