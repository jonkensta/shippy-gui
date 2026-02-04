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
from shippy_gui.settings_dialog import SettingsDialog


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
            "Please fill in your API keys and return address."
        )
        if not _run_settings_dialog(config_path):
            sys.exit(1)
        return _reload_config_or_exit(config_path)

    try:
        return load_config(config_path)
    except ValidationError as e:
        _show_config_error(
            f"Config file is invalid or incomplete:\n\n{e}\n\n"
            "Please update the settings."
        )
        if not _run_settings_dialog(config_path):
            sys.exit(1)
        return _reload_config_or_exit(config_path)
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


def _run_settings_dialog(config_path: str) -> bool:
    """Open settings dialog to let user fix configuration."""
    dialog = SettingsDialog(config_path)
    return bool(dialog.exec())


def _reload_config_or_exit(config_path: str):
    """Reload config after settings; exit if still invalid."""
    try:
        return load_config(config_path)
    except ValidationError as e:
        _show_config_error(
            f"Config file is still invalid or incomplete:\n\n{e}\n\nThe application will exit.",
        )
        sys.exit(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        _show_config_error(
            f"Failed to read config file:\n\n{e}\n\nThe application will exit.",
        )
        sys.exit(1)


def _initialize_config(config_path: str) -> None:
    """Create a starter config.ini in the working directory."""
    contents = _load_packaged_example_config()
    if not contents:
        raise RuntimeError(
            "Unable to load packaged config.example.ini. Please reinstall shippy-gui."
        )

    with open(config_path, "w", encoding="utf-8") as dest:
        dest.write(contents)


def _load_packaged_example_config() -> str:
    """Load the packaged config.example.ini contents."""
    try:
        from importlib import resources  # pylint: disable=import-outside-toplevel

        with (
            resources.files("shippy_gui")
            .joinpath("config.example.ini")
            .open("r", encoding="utf-8") as handle
        ):
            return handle.read()
    except Exception:  # pylint: disable=broad-exception-caught
        return ""


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
