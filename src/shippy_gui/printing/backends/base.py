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

    @staticmethod
    def parse_name_identifier(  # pylint: disable=unused-argument
        printer_name: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Split a queue name's trailing USB identifier, if it carries one.

        Naming conventions are a property of the platform's printer subsystem,
        so the rule lives with the backend that matches against it. Callers get
        the same answer the backend used to decide whether the queue was worth
        listing, which is what keeps reported metadata from disagreeing with
        the discovery it describes.

        Returns:
            ``(vid_pid, serial)`` where at most one is set, or ``(None, None)``
            when the platform has no such convention or the name carries no
            identifier.
        """
        return None, None
