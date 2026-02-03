"""Linux printer backend using CUPS."""

import logging
import subprocess
import tempfile
from typing import Optional

from PIL import Image

from shippy_gui.core.constants import (
    DEFAULT_PRINT_DPI,
    PAGE_HEIGHT_POINTS,
    PAGE_MARGIN_POINTS,
    PAGE_WIDTH_POINTS,
    POINTS_PER_INCH,
    PRINT_SCALE_FACTOR,
)
from shippy_gui.printing.backends.base import PrinterBackend

logger = logging.getLogger(__name__)


class LinuxPrinterBackend(PrinterBackend):
    """Linux printer backend using CUPS/lpstat."""

    def get_available_printers(self) -> list[str]:
        """Get available printers using pycups or lpstat fallback."""
        printers = []

        # Try using pycups first (more reliable)
        try:
            import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

            conn = cups.Connection()  # pylint: disable=c-extension-no-member
            printers_dict = conn.getPrinters()
            printers = list(printers_dict.keys())
            return printers
        except ImportError:
            logger.debug("pycups not available, falling back to lpstat")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug(
                "CUPS connection failed, falling back to lpstat", exc_info=True
            )

        # Fallback to lpstat command
        try:
            result = subprocess.run(
                ["lpstat", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("printer "):
                        parts = line.split()
                        if len(parts) >= 2:
                            printers.append(parts[1])
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("lpstat command failed", exc_info=True)

        return printers

    def get_default_printer(self) -> Optional[str]:
        """Get default printer using pycups or lpstat fallback."""
        try:
            import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

            conn = cups.Connection()  # pylint: disable=c-extension-no-member
            return conn.getDefault()
        except ImportError:
            logger.debug("pycups not available for default printer lookup")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug(
                "CUPS connection failed for default printer lookup", exc_info=True
            )

        # Fallback to lpstat
        try:
            result = subprocess.run(
                ["lpstat", "-d"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                line = result.stdout.strip()
                if ":" in line:
                    return line.split(":")[-1].strip()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("lpstat -d command failed", exc_info=True)

        return None

    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Print image using lp command."""
        # Auto-rotate if landscape
        if img.size[0] > img.size[1]:
            img = img.rotate(90, expand=True)

        # Scale image for printer
        scaled_img = self._scale_image_for_printer(img, printer_name)

        # Save to temp file and print
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            try:
                scaled_img.save(tmpfile.name)
                tmpfile.close()

                result = subprocess.run(
                    ["lp", "-d", printer_name, "-o", "fit-to-page", tmpfile.name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

                if result.returncode != 0:
                    raise RuntimeError(f"Print command failed: {result.stderr}")

            finally:
                import os  # pylint: disable=import-outside-toplevel

                os.remove(tmpfile.name)

    def _scale_image_for_printer(  # pylint: disable=too-many-locals
        self, img: Image.Image, printer_name: str
    ) -> Image.Image:
        """Scale image to fit printer's printable area and center on page."""
        try:
            import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

            conn = cups.Connection()  # pylint: disable=c-extension-no-member
            printers = conn.getPrinters()

            if printer_name not in printers:
                return img

            # Calculate printable area (letter size with margins)
            printable_width_pts = PAGE_WIDTH_POINTS - (2 * PAGE_MARGIN_POINTS)
            printable_height_pts = PAGE_HEIGHT_POINTS - (2 * PAGE_MARGIN_POINTS)

            # Convert points to pixels
            printable_width_px = int(
                printable_width_pts * DEFAULT_PRINT_DPI / POINTS_PER_INCH
            )
            printable_height_px = int(
                printable_height_pts * DEFAULT_PRINT_DPI / POINTS_PER_INCH
            )

            # Calculate scaling
            ratios = [
                printable_width_px / img.size[0],
                printable_height_px / img.size[1],
            ]
            scale = PRINT_SCALE_FACTOR * min(ratios)

            # Scale the image
            scaled_width = int(img.size[0] * scale)
            scaled_height = int(img.size[1] * scale)

            if scaled_width > 0 and scaled_height > 0:
                scaled_img = img.resize(
                    (scaled_width, scaled_height), Image.Resampling.LANCZOS
                )

                # Create a full-page canvas
                total_width_px = int(
                    PAGE_WIDTH_POINTS * DEFAULT_PRINT_DPI / POINTS_PER_INCH
                )
                total_height_px = int(
                    PAGE_HEIGHT_POINTS * DEFAULT_PRINT_DPI / POINTS_PER_INCH
                )
                canvas = Image.new("RGB", (total_width_px, total_height_px), "white")

                # Center the scaled image
                x_offset = int((total_width_px - scaled_width) / 2)
                y_offset = int((total_height_px - scaled_height) / 2)
                canvas.paste(scaled_img, (x_offset, y_offset))

                return canvas

        except ImportError:
            logger.debug("pycups not available for scaling, using original image")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Image scaling failed, using original image", exc_info=True)

        return img
