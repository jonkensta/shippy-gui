"""Entry point for shippy-gui application."""

import os
import sys

from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.font import apply_font_size, get_font_size_from_config
from shippy_gui.main_window import MainWindow


def main():
    """Launch the shippy-gui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Shippy GUI")
    app.setOrganizationName("Inside Books Project")

    cwd = os.getcwd()
    config_path = os.path.join(cwd, "config.ini")
    example_config_path = os.path.join(cwd, "config.example.ini")

    # Use existing config.ini if it exists, otherwise fall back to example for loading
    active_config_path = (
        config_path if os.path.exists(config_path) else example_config_path
    )

    # Apply configured font size
    font_size = get_font_size_from_config(active_config_path)
    apply_font_size(app, font_size)

    # Note: We pass the intended config_path to MainWindow so that when the user
    # saves settings, they are written to config.ini, not config.example.ini.
    window = MainWindow(config_path=config_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
