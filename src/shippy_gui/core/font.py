"""Font utilities for shippy-gui application."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication  # type: ignore[import-untyped]


def apply_font_size(app: "QApplication", size: int) -> None:
    """Apply font size to the application.

    Args:
        app: The QApplication instance
        size: Font size in points
    """
    font = app.font()
    font.setPointSize(size)
    app.setFont(font)
