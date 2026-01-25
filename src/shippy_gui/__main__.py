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

    config_path = os.path.join(os.getcwd(), "config.ini")

    # Apply configured font size
    font_size = get_font_size_from_config(config_path)
    apply_font_size(app, font_size)

    window = MainWindow(config_path=config_path)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
