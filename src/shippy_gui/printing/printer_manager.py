"""Printer detection and management for shippy-gui."""

import platform
import subprocess
from typing import Optional


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
