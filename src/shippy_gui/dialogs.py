"""Shared Qt presentation helpers.

``core`` reports failures as data; these helpers put them on screen. Keeping
the QMessageBox calls here is what lets ``core.config_manager`` stay Qt-free.
"""

from typing import Optional

from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QMessageBox,
    QWidget,
)

from shippy_gui.core.config_manager import ConfigResult


def show_error(parent: Optional[QWidget], title: str, message: str) -> None:
    """Display a blocking error dialog."""
    QMessageBox.critical(parent, title, message)


def show_config_error(parent: Optional[QWidget], result: ConfigResult) -> None:
    """Display a failed configuration load or save."""
    show_error(parent, result.title, result.message)
