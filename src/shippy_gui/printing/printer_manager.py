"""Printer detection and management for shippy-gui."""

import platform
import subprocess
import tempfile
from typing import Optional
from PIL import Image


def get_available_printers() -> list[str]:
    """Get list of available printers on the system.

    Returns:
        List of printer names. Empty list if no printers found or on error.
    """
    system = platform.system()

    if system == "Linux":
        return _get_linux_printers()
    if system == "Windows":
        return _get_windows_printers()
    return []


def get_default_printer() -> Optional[str]:
    """Get the system default printer.

    Returns:
        Default printer name, or None if no default is set.
    """
    system = platform.system()

    if system == "Linux":
        return _get_linux_default_printer()
    if system == "Windows":
        return _get_windows_default_printer()
    return None


def _get_linux_printers() -> list[str]:
    """Get available printers on Linux using lpstat or pycups."""
    printers = []

    # Try using pycups first (more reliable)
    try:
        import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

        conn = cups.Connection()  # pylint: disable=c-extension-no-member
        printers_dict = conn.getPrinters()
        printers = list(printers_dict.keys())
        return printers
    except ImportError:
        # pycups not available, fall back to lpstat
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        # CUPS connection failed, fall back to lpstat
        pass

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
                    # Format: "printer PrinterName is idle..."
                    parts = line.split()
                    if len(parts) >= 2:
                        printers.append(parts[1])
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):  # pylint: disable=broad-exception-caught
        pass

    return printers


def _get_linux_default_printer() -> Optional[str]:
    """Get default printer on Linux."""
    try:
        import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

        conn = cups.Connection()  # pylint: disable=c-extension-no-member
        return conn.getDefault()
    except ImportError:
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        pass

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
            # Format: "system default destination: PrinterName"
            line = result.stdout.strip()
            if ":" in line:
                return line.split(":")[-1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):  # pylint: disable=broad-exception-caught
        pass

    return None


def _get_windows_printers() -> list[str]:
    """Get available printers on Windows."""
    printers = []

    try:
        import win32print  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel

        # Enumerate all printers
        printer_info = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        printers = [printer[2] for printer in printer_info]
    except ImportError:
        # win32print not available
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return printers


def _get_windows_default_printer() -> Optional[str]:
    """Get default printer on Windows."""
    try:
        import win32print  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel

        return win32print.GetDefaultPrinter()
    except ImportError:
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return None


def print_image(img: Image.Image, printer_name: str) -> None:
    """Print an image to the specified printer.

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use

    Raises:
        RuntimeError: If printing fails
    """
    system = platform.system()

    if system == "Linux":
        _print_image_linux(img, printer_name)
    elif system == "Windows":
        _print_image_windows(img, printer_name)
    else:
        raise RuntimeError(f"Printing not supported on {system}")


def _print_image_linux(img: Image.Image, printer_name: str) -> None:
    """Print image on Linux using CUPS.

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use
    """
    # Auto-rotate if landscape
    if img.size[0] > img.size[1]:
        img = img.rotate(90, expand=True)

    # Try to get printer paper size and scale image appropriately
    scaled_img = _scale_image_for_printer_linux(img, printer_name)

    # Save to temp file and print with lp command
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
        try:
            scaled_img.save(tmpfile.name)
            tmpfile.close()

            # Use lp command to print
            # -o fit-to-page ensures it fits on the page
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
            import os

            os.remove(tmpfile.name)


def _scale_image_for_printer_linux(img: Image.Image, printer_name: str) -> Image.Image:
    """Scale image to fit printer's printable area and center it on the page.

    Args:
        img: PIL Image to scale
        printer_name: Name of the printer

    Returns:
        Full-page image with scaled label centered, or original if scaling info unavailable
    """
    try:
        import cups  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

        conn = cups.Connection()  # pylint: disable=c-extension-no-member
        printers = conn.getPrinters()

        if printer_name not in printers:
            # Printer not found, return original
            return img

        # Get printer attributes
        printer_attrs = printers[printer_name]

        # Try to get page size from printer
        # CUPS uses points (1/72 inch) for dimensions
        # Common sizes: Letter = 612x792 pts, Legal = 612x1008 pts
        # Note: printer-make-and-model could be used for PPD lookup but is not currently used
        _ = printer_attrs.get("printer-make-and-model", "")

        # Get default media size
        # This is a simplified approach - full PPD parsing would be more accurate
        # Default to letter size (8.5" x 11" = 612 x 792 points)
        page_width_pts = 612
        page_height_pts = 792

        # Assume 0.25" margins on all sides (18 points)
        margin_pts = 18
        printable_width_pts = page_width_pts - (2 * margin_pts)
        printable_height_pts = page_height_pts - (2 * margin_pts)

        # Convert points to pixels assuming 300 DPI
        # 1 point = 1/72 inch, so points * DPI / 72 = pixels
        dpi = 300
        printable_width_px = int(printable_width_pts * dpi / 72)
        printable_height_px = int(printable_height_pts * dpi / 72)

        # Calculate scaling (similar to Windows approach)
        ratios = [printable_width_px / img.size[0], printable_height_px / img.size[1]]
        scale = 0.95 * min(ratios)  # 95% to avoid clipping

        # Scale the image
        scaled_width = int(img.size[0] * scale)
        scaled_height = int(img.size[1] * scale)

        if scaled_width > 0 and scaled_height > 0:
            scaled_img = img.resize(
                (scaled_width, scaled_height), Image.Resampling.LANCZOS
            )

            # Create a full-page canvas (total physical page size)
            total_width_px = int(page_width_pts * dpi / 72)
            total_height_px = int(page_height_pts * dpi / 72)
            canvas = Image.new("RGB", (total_width_px, total_height_px), "white")

            # Calculate position to center the scaled image
            x_offset = int((total_width_px - scaled_width) / 2)
            y_offset = int((total_height_px - scaled_height) / 2)

            # Paste the scaled image onto the center of the canvas
            canvas.paste(scaled_img, (x_offset, y_offset))

            return canvas

    except ImportError:
        # pycups not available, return original and let lp handle it
        pass
    except Exception:  # pylint: disable=broad-exception-caught
        # Any error in scaling, return original
        pass

    return img


def _print_image_windows(img: Image.Image, printer_name: str) -> None:
    """Print image on Windows using win32print.

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use
    """
    try:
        import win32ui  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel
        from PIL import ImageWin  # pylint: disable=import-outside-toplevel
    except ImportError:
        # Fallback to powershell if win32 modules not available
        _print_image_windows_fallback(img)
        return

    # Create printer device context
    context = win32ui.CreateDC()
    context.CreatePrinterDC(printer_name)

    try:
        # Auto-rotate if landscape
        if img.size[0] > img.size[1]:
            img = img.rotate(90, expand=True)

        # Get printable area
        horzres = context.GetDeviceCaps(8)  # HORZRES
        vertres = context.GetDeviceCaps(10)  # VERTRES

        # Calculate scaling
        ratios = [horzres / img.size[0], vertres / img.size[1]]
        scale = 0.95 * min(ratios)  # 95% to avoid clipping

        # Get total area for centering
        total_w = context.GetDeviceCaps(110)  # PHYSICALWIDTH
        total_h = context.GetDeviceCaps(111)  # PHYSICALHEIGHT

        # Calculate scaled size and position
        scaled_w, scaled_h = [int(scale * i) for i in img.size]
        lhs_x = int((total_w - scaled_w) / 2)
        lhs_y = int((total_h - scaled_h) / 2)
        rhs_x = lhs_x + scaled_w
        rhs_y = lhs_y + scaled_h

        # Print the image
        context.StartDoc("Shipping Label")
        context.StartPage()

        dib = ImageWin.Dib(img)
        dib.draw(context.GetHandleOutput(), (lhs_x, lhs_y, rhs_x, rhs_y))

        context.EndPage()
        context.EndDoc()

    finally:
        context.DeleteDC()


def _print_image_windows_fallback(img: Image.Image) -> None:
    """Fallback Windows printing using default image viewer.

    Args:
        img: PIL Image to print
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
        try:
            img.save(tmpfile.name)
            tmpfile.close()

            subprocess.check_call(["powershell", "-c", tmpfile.name])

        finally:
            import os

            os.remove(tmpfile.name)
