"""Null printer backend for unsupported platforms."""

import platform
from typing import Optional

from PIL import Image

from shippy_gui.printing.backends.base import PrinterBackend


class NullPrinterBackend(PrinterBackend):
    """Backend that reports no printers and rejects print requests."""

    def get_available_printers(self) -> list[str]:
        """Return empty list."""
        return []

    def get_default_printer(self) -> Optional[str]:
        """Return no default printer."""
        return None

    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Raise for unsupported platforms."""
        raise RuntimeError(f"Printing not supported on {platform.system()}")
