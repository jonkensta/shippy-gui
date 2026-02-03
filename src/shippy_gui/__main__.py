"""Entry point for shippy-gui application."""

import sys

from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.font import apply_font_size
from shippy_gui.core.config import get_font_size_from_path, resolve_config_paths
from shippy_gui.main_window import MainWindow


def main():
    """Launch the shippy-gui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Shippy GUI")
    app.setOrganizationName("Inside Books Project")

    config_paths = resolve_config_paths()

    # Apply configured font size
    font_size = get_font_size_from_path(config_paths.active_load_path)
    apply_font_size(app, font_size)

    # Note: We pass the intended config_path to MainWindow so that when the user
    # saves settings, they are written to config.ini, not config.example.ini.
    window = MainWindow(config_path=config_paths.config_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
