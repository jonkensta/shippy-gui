"""Base class for printer backends."""

from abc import ABC, abstractmethod
from typing import Optional

from PIL import Image


class PrinterBackend(ABC):
    """Abstract base class for platform-specific printer backends."""

    @abstractmethod
    def get_available_printers(self) -> list[str]:
        """Get list of available printers.

        Returns:
            List of printer names.
        """

    @abstractmethod
    def get_default_printer(self) -> Optional[str]:
        """Get the system default printer.

        Returns:
            Default printer name, or None if no default.
        """

    @abstractmethod
    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Print an image to the specified printer.

        Args:
            img: PIL Image to print.
            printer_name: Name of the printer.

        Raises:
            RuntimeError: If printing fails.
        """
