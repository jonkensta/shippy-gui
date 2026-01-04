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
    elif system == "Windows":
        return _get_windows_printers()
    else:
        return []


def get_default_printer() -> Optional[str]:
    """Get the system default printer.

    Returns:
        Default printer name, or None if no default is set.
    """
    system = platform.system()

    if system == "Linux":
        return _get_linux_default_printer()
    elif system == "Windows":
        return _get_windows_default_printer()
    else:
        return None


def _get_linux_printers() -> list[str]:
    """Get available printers on Linux using lpstat or pycups."""
    printers = []

    # Try using pycups first (more reliable)
    try:
        import cups

        conn = cups.Connection()
        printers_dict = conn.getPrinters()
        printers = list(printers_dict.keys())
        return printers
    except ImportError:
        # pycups not available, fall back to lpstat
        pass
    except Exception:
        # CUPS connection failed, fall back to lpstat
        pass

    # Fallback to lpstat command
    try:
        result = subprocess.run(
            ["lpstat", "-p"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("printer "):
                    # Format: "printer PrinterName is idle..."
                    parts = line.split()
                    if len(parts) >= 2:
                        printers.append(parts[1])
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return printers


def _get_linux_default_printer() -> Optional[str]:
    """Get default printer on Linux."""
    try:
        import cups

        conn = cups.Connection()
        return conn.getDefault()
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback to lpstat
    try:
        result = subprocess.run(
            ["lpstat", "-d"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Format: "system default destination: PrinterName"
            line = result.stdout.strip()
            if ":" in line:
                return line.split(":")[-1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def _get_windows_printers() -> list[str]:
    """Get available printers on Windows."""
    printers = []

    try:
        import win32print

        # Enumerate all printers
        printer_info = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        printers = [printer[2] for printer in printer_info]
    except ImportError:
        # win32print not available
        pass
    except Exception:
        pass

    return printers


def _get_windows_default_printer() -> Optional[str]:
    """Get default printer on Windows."""
    try:
        import win32print

        return win32print.GetDefaultPrinter()
    except ImportError:
        pass
    except Exception:
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
    # Save to temp file and print with lp command
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
        try:
            img.save(tmpfile.name)
            tmpfile.close()

            # Use lp command to print
            result = subprocess.run(
                ["lp", "-d", printer_name, tmpfile.name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Print command failed: {result.stderr}")

        finally:
            import os
            os.remove(tmpfile.name)


def _print_image_windows(img: Image.Image, printer_name: str) -> None:
    """Print image on Windows using win32print.

    Args:
        img: PIL Image to print
        printer_name: Name of the printer to use
    """
    try:
        import win32print
        import win32ui
        from PIL import ImageWin
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
