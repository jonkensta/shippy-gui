"""Windows printer backend using win32print."""

import logging
import subprocess
import tempfile
from typing import Optional

from PIL import Image

from shippy_gui.core.constants import (
    PRINT_SCALE_FACTOR,
    WIN_DEVCAP_HORZRES,
    WIN_DEVCAP_PHYSICALHEIGHT,
    WIN_DEVCAP_PHYSICALWIDTH,
    WIN_DEVCAP_VERTRES,
)
from shippy_gui.printing.backends.base import PrinterBackend

logger = logging.getLogger(__name__)


class WindowsPrinterBackend(PrinterBackend):
    """Windows printer backend using win32print/win32ui."""

    def get_available_printers(self) -> list[str]:
        """Get available printers using win32print."""
        printers = []

        try:
            import win32print  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel

            printer_info = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            printers = [printer[2] for printer in printer_info]
        except ImportError:
            logger.debug("win32print not available")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Windows printer enumeration failed", exc_info=True)

        return printers

    def get_default_printer(self) -> Optional[str]:
        """Get default printer using win32print."""
        try:
            import win32print  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel

            return win32print.GetDefaultPrinter()
        except ImportError:
            logger.debug("win32print not available for default printer lookup")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Windows default printer lookup failed", exc_info=True)

        return None

    def print_image(  # pylint: disable=too-many-locals
        self, img: Image.Image, printer_name: str
    ) -> None:
        """Print image using win32ui."""
        try:
            import win32ui  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel
            from PIL import ImageWin  # pylint: disable=import-outside-toplevel
        except ImportError:
            self._print_fallback(img)
            return

        # Create printer device context
        context = win32ui.CreateDC()
        context.CreatePrinterDC(printer_name)

        try:
            # Auto-rotate if landscape
            if img.size[0] > img.size[1]:
                img = img.rotate(90, expand=True)

            # Calculate print position
            print_rect = self._calculate_print_rect(context, img.size)

            # Print the image
            context.StartDoc("Shipping Label")
            context.StartPage()

            dib = ImageWin.Dib(img)
            dib.draw(context.GetHandleOutput(), print_rect)

            context.EndPage()
            context.EndDoc()

        finally:
            context.DeleteDC()

    def _calculate_print_rect(self, context, img_size: tuple[int, int]) -> tuple:
        """Calculate the rectangle for centered, scaled printing.

        Args:
            context: Win32 device context.
            img_size: Tuple of (width, height) of the image.

        Returns:
            Tuple of (left, top, right, bottom) for the print area.
        """
        # Get printable area
        horzres = context.GetDeviceCaps(WIN_DEVCAP_HORZRES)
        vertres = context.GetDeviceCaps(WIN_DEVCAP_VERTRES)

        # Calculate scaling
        ratios = [horzres / img_size[0], vertres / img_size[1]]
        scale = PRINT_SCALE_FACTOR * min(ratios)

        # Get total area for centering
        total_w = context.GetDeviceCaps(WIN_DEVCAP_PHYSICALWIDTH)
        total_h = context.GetDeviceCaps(WIN_DEVCAP_PHYSICALHEIGHT)

        # Calculate scaled size and position
        scaled_w = int(scale * img_size[0])
        scaled_h = int(scale * img_size[1])
        lhs_x = int((total_w - scaled_w) / 2)
        lhs_y = int((total_h - scaled_h) / 2)

        return (lhs_x, lhs_y, lhs_x + scaled_w, lhs_y + scaled_h)

    def _print_fallback(self, img: Image.Image) -> None:
        """Fallback Windows printing using PowerShell."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            try:
                img.save(tmpfile.name)
                tmpfile.close()

                subprocess.check_call(["powershell", "-c", tmpfile.name])

            finally:
                import os  # pylint: disable=import-outside-toplevel

                os.remove(tmpfile.name)
