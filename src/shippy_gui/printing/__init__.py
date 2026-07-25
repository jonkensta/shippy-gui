"""Printing module for shippy-gui.

This module provides platform-independent printing functionality.
"""

from shippy_gui.printing.models import PrintDialogResult, PrinterInfo
from shippy_gui.printing.printer_manager import (
    get_available_printers,
    print_image,
    print_image_with_dialog,
)
from shippy_gui.printing.printer_service import PrinterService, get_printer_service

__all__ = [
    "get_available_printers",
    "print_image",
    "print_image_with_dialog",
    "PrintDialogResult",
    "PrinterInfo",
    "PrinterService",
    "get_printer_service",
]
