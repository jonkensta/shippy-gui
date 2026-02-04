"""Entry point for shippy-gui application."""

import logging
import os
import sys

from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from pydantic import ValidationError

from shippy_gui.core.config import load_config
from shippy_gui.core.constants import DEFAULT_LOG_FILENAME
from shippy_gui.core.logging import configure_logging
from shippy_gui.core.font import apply_font_size
from shippy_gui.main_window import MainWindow


def main():
    """Launch the shippy-gui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Shippy GUI")
    app.setOrganizationName("Inside Books Project")

    config_path = os.path.join(os.getcwd(), "config.ini")
    config = _load_required_config(config_path)

    _configure_app_logging(config_path, config)

    # Apply configured font size
    apply_font_size(app, config.get_font_size())

    # Note: We pass the intended config_path to MainWindow so that when the user
    # saves settings, they are written to config.ini, not config.example.ini.
    window = MainWindow(config_path=config_path)
    window.show()

    sys.exit(app.exec())


def _load_required_config(config_path: str):
    """Load config.ini or exit if missing/invalid."""
    if not os.path.exists(config_path):
        _initialize_config(config_path)
        _show_config_error(
            "A new config.ini was created in this folder.\n\n"
            "Please open Settings and fill in your API keys and return address, "
            "then restart the application."
        )
        sys.exit(1)

    try:
        return load_config(config_path)
    except ValidationError as e:
        _show_config_error(
            f"Config file is invalid or incomplete:\n\n{e}\n\nThe application will exit.",
        )
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _show_config_error(
            f"Failed to read config file:\n\n{e}\n\nThe application will exit.",
        )
        sys.exit(1)


def _show_config_error(message: str) -> None:
    """Display a blocking configuration error."""
    from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module,import-outside-toplevel
        QMessageBox,
    )

    QMessageBox.critical(None, "Configuration Error", message)


def _initialize_config(config_path: str) -> None:
    """Create a starter config.ini in the working directory."""
    example_path = os.path.join(os.getcwd(), "config.example.ini")
    if os.path.exists(example_path):
        with open(example_path, "r", encoding="utf-8") as src:
            contents = src.read()
        with open(config_path, "w", encoding="utf-8") as dest:
            dest.write(contents)
        return

    with open(config_path, "w", encoding="utf-8") as dest:
        dest.write("[ui]\nfont_size = 11\ndefault_weight = 3\nlog_file = shippy.log\n")
        dest.write("\n[easypost]\napikey =\n")
        dest.write("\n[googlemaps]\napikey =\n")
        dest.write(
            "\n[return_address]\nname =\nstreet1 =\nstreet2 =\ncity =\nstate =\nzipcode =\n"
        )


def _configure_app_logging(config_path: str, config) -> None:
    """Configure logging using config settings."""
    config_dir = os.path.dirname(config_path)
    default_log_path = os.path.join(config_dir, DEFAULT_LOG_FILENAME)

    log_path = default_log_path
    try:
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
