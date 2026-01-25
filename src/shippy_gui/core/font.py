"""Font utilities for shippy-gui application."""

import configparser
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped]


def get_font_size_from_config(config_path: str) -> int:
    """Read font size from config file.

    Args:
        config_path: Path to the config.ini file

    Returns:
        Font size in points, defaults to 11 if not configured
    """
    default_size = 11
    if not os.path.exists(config_path):
        return default_size

    config_parser = configparser.ConfigParser()
    config_parser.read(config_path)

    try:
        return config_parser.getint("ui", "font_size", fallback=default_size)
    except (ValueError, configparser.Error):
        return default_size


def apply_font_size(app: "QApplication", size: int) -> None:
    """Apply font size to the application.

    Args:
        app: The QApplication instance
        size: Font size in points
    """
    font = app.font()
    font.setPointSize(size)
    app.setFont(font)
