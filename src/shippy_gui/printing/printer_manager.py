"""Printer discovery and printing for shippy-gui.

Discovery and direct printing are thin adapters over the shared
``ibp_printing`` library, which owns the platform backends, the USB label
printer matching rules, and the verbose printer logs. Only the Qt print dialog
path lives here.
"""

import logging
from typing import Optional

import ibp_printing
from PIL import Image, ImageQt
from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtGui import QPainter  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtPrintSupport import QPrintDialog, QPrinter  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QWidget  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import PRINT_JOB_NAME, PRINT_TRACK_TIMEOUT_S
from shippy_gui.printing.models import PrinterInfo

logger = logging.getLogger(__name__)


def get_available_printers() -> list[PrinterInfo]:
    """Get usable label printers, best first.

    On Windows these are queues whose name ends in a USB ``VID:PID`` suffix and
    whose USB device is present; on Linux every CUPS queue is listed.

    Returns:
        List of discovered printers. Empty list if none are found or on error.
    """
    try:
        candidates = ibp_printing.discover().usable
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Printer discovery failed")
        return []
    return [PrinterInfo.from_candidate(candidate) for candidate in candidates]


def get_default_printer() -> Optional[str]:
    """Get the system default printer.

    Returns:
        Default printer name, or None if no default is set.
    """
    try:
        return ibp_printing.get_default_printer()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Default printer lookup failed")
        return None


def print_image(
    img: Image.Image, printer_name: str, *, job_name: Optional[str] = None
) -> ibp_printing.PrintResult:
    """Print an image to the specified printer.

    Blocks for up to ``PRINT_TRACK_TIMEOUT_S`` while the spooled job is
    followed, so call it from a worker thread. The tracked outcome is logged
    but does not raise: once the spooler has accepted the job, the label may
    still come out (e.g. after paper is reloaded).

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use
        job_name: Optional spooler job name (defaults to ``PRINT_JOB_NAME``)

    Returns:
        The ibp-printing result, including the tracked job outcome.

    Raises:
        ibp_printing.PrintError: (a RuntimeError) if the job could not be spooled
    """
    result = ibp_printing.print_image(
        img,
        printer_name,
        job_name=job_name or PRINT_JOB_NAME,
        track_timeout_s=PRINT_TRACK_TIMEOUT_S,
    )
    if not result.outcome.ok:
        logger.warning(
            "Print job on %s ended as %s: %s",
            printer_name,
            result.outcome.value,
            "; ".join(result.history) or "(no history)",
        )
    return result


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
        logger.info("Printing via system dialog to %s", printer.printerName())
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
