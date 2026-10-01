"""Printing module for shippy-gui.

Thin adapters over the shared ``ibp_printing`` library plus the Qt print dialog.
"""

from shippy_gui.printing.printer_manager import (
    get_available_printers,
    get_default_printer,
    print_image,
    print_image_with_dialog,
)

__all__ = [
    "get_available_printers",
    "get_default_printer",
    "print_image",
    "print_image_with_dialog",
]
