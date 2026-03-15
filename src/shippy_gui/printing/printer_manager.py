"""Printer detection and management for shippy-gui.

This module provides the public API for printer operations. It delegates
platform-specific operations to the PrinterService abstraction.
"""

import logging
from typing import Optional

from PIL import Image, ImageQt
from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtGui import QPainter  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtPrintSupport import QPrintDialog, QPrinter  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QWidget  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.printing.models import PrinterInfo
from shippy_gui.printing.printer_service import get_printer_service

logger = logging.getLogger(__name__)


def get_available_printers() -> list[PrinterInfo]:
    """Get available printers on the system.

    Returns:
        List of discovered printers. Empty list if no printers found or on error.
    """
    return get_printer_service().get_available_printers()


def get_default_printer() -> Optional[str]:
    """Get the system default printer.

    Returns:
        Default printer name, or None if no default is set.
    """
    return get_printer_service().get_default_printer()


def print_image(img: Image.Image, printer_name: str) -> None:
    """Print an image to the specified printer.

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use

    Raises:
        RuntimeError: If printing fails
    """
    get_printer_service().print_image(img, printer_name)


def print_image_with_dialog(
    img: Image.Image,
    parent_widget: QWidget,
    preferred_printer_name: Optional[str] = None,
) -> str:
    """Show system print dialog and print image if accepted.

    This function uses Qt's QPrintDialog for cross-platform dialog printing.

    Args:
        img: PIL Image to print
        parent_widget: Parent widget for the dialog
        preferred_printer_name: Optional name of the printer to pre-select

    Returns:
        One of "printed", "failed", or "canceled"
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if preferred_printer_name:
        printer.setPrinterName(preferred_printer_name)

    dialog = QPrintDialog(printer, parent_widget)
    dialog.setWindowTitle("Print Shipping Label")

    if dialog.exec() == QPrintDialog.DialogCode.Accepted:
        if _print_with_qprinter(img, printer):
            return "printed"
        return "failed"

    return "canceled"


def _print_with_qprinter(img: Image.Image, printer: QPrinter) -> bool:
    """Print an image using a QPrinter.

    Args:
        img: PIL Image to print
        printer: Configured QPrinter object

    Returns:
        True if printing succeeded, False otherwise
    """
    try:
        # Auto-rotate if landscape
        if img.size[0] > img.size[1]:
            img = img.rotate(90, expand=True)

        # Convert PIL to QImage
        q_img = ImageQt.ImageQt(img)

        painter = QPainter()
        if not painter.begin(printer):
            logger.warning("QPainter.begin() failed for QPrinter dialog print.")
            return False

        try:
            # Get dimensions
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            size = q_img.size()
            size.scale(rect.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)

            # Center on page
            painter.setViewport(
                int((rect.width() - size.width()) / 2),
                int((rect.height() - size.height()) / 2),
                size.width(),
                size.height(),
            )
            painter.setWindow(q_img.rect())

            # Draw the image
            painter.drawImage(0, 0, q_img)

        finally:
            painter.end()

        return True

    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Dialog print failed during QPrinter rendering.")
        return False
