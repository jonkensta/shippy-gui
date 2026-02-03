"""Platform-independent printer service abstraction."""

import logging
import platform
from typing import Optional

from PIL import Image

from shippy_gui.printing.backends.base import PrinterBackend

logger = logging.getLogger(__name__)


class PrinterService:
    """High-level printer service that delegates to platform-specific backends.

    This service provides a unified API for printer operations while hiding
    platform-specific implementation details.
    """

    def __init__(self, backend: Optional[PrinterBackend] = None):
        """Initialize the printer service.

        Args:
            backend: Optional printer backend. If not provided, auto-detects
                    based on the current platform.
        """
        if backend is not None:
            self._backend = backend
        else:
            self._backend = self._create_backend_for_platform()

    @staticmethod
    def _create_backend_for_platform() -> PrinterBackend:
        """Create the appropriate backend for the current platform.

        Returns:
            Platform-specific PrinterBackend instance.

        Raises:
            RuntimeError: If the platform is not supported.
        """
        system = platform.system()

        if system == "Linux":
            from shippy_gui.printing.backends.linux import (  # pylint: disable=import-outside-toplevel
                LinuxPrinterBackend,
            )

            return LinuxPrinterBackend()

        if system == "Windows":
            from shippy_gui.printing.backends.windows import (  # pylint: disable=import-outside-toplevel
                WindowsPrinterBackend,
            )

            return WindowsPrinterBackend()

        # Return a null backend for unsupported platforms
        logger.warning("Unsupported platform for printing: %s", system)
        return NullPrinterBackend()

    def get_available_printers(self) -> list[str]:
        """Get list of available printers.

        Returns:
            List of printer names.
        """
        return self._backend.get_available_printers()

    def get_default_printer(self) -> Optional[str]:
        """Get the system default printer.

        Returns:
            Default printer name, or None if no default.
        """
        return self._backend.get_default_printer()

    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Print an image to the specified printer.

        Args:
            img: PIL Image to print.
            printer_name: Name of the printer.

        Raises:
            RuntimeError: If printing fails.
        """
        self._backend.print_image(img, printer_name)


class NullPrinterBackend(PrinterBackend):
    """Null backend for unsupported platforms."""

    def get_available_printers(self) -> list[str]:
        """Return empty list."""
        return []

    def get_default_printer(self) -> Optional[str]:
        """Return None."""
        return None

    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Raise error for unsupported platform."""
        raise RuntimeError(f"Printing not supported on {platform.system()}")


# Module-level singleton for convenience
_DEFAULT_SERVICE: Optional[PrinterService] = None


def get_printer_service() -> PrinterService:
    """Get the default printer service instance.

    Returns:
        The default PrinterService singleton.
    """
    global _DEFAULT_SERVICE  # pylint: disable=global-statement
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = PrinterService()
    return _DEFAULT_SERVICE
