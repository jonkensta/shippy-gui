"""Windows printer backend using win32print."""

import contextlib
import logging
import re
import subprocess
import tempfile
from typing import Iterator, Optional

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

# Trailing USB identifiers in a Windows printer queue name, separated from the
# rest of the name by a space, hyphen, or underscore:
#   * "PM-2411-BT 2E3C:5760"              -> VID:PID, shared by every unit of a
#     model, so it cannot tell two same-model printers apart (legacy), or
#   * "Front-Desk PM-2411-BT Q529E65K52"  -> a USB serial, unique per unit.
NAME_VID_PID_PATTERN = re.compile(r"[\s\-_]([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})$")
NAME_SERIAL_PATTERN = re.compile(r"[\s\-_]([0-9A-Za-z]{6,})$")

# Top-level USB device-instance ID, e.g. "USB\VID_2E3C&PID_5760\Q529E65K52".
# The trailing segment is the per-unit serial (or, lacking one, a port-based
# instance path). An optional "&REV_xxxx" is allowed, but interface/child nodes
# ("...&MI_00\...") do not match, so each match is one physical device rather
# than several PnP nodes for the same printer.
USB_INSTANCE_PATTERN = re.compile(
    r"^USB\\VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})"
    r"(?:&REV_[0-9A-Fa-f]{4})?\\([^\\]+)$",
    re.IGNORECASE,
)

# VID/PID prefix of a device-instance ID. Used to scope a serial match to a real
# USB device and read its VID/PID; tolerant of composite and "&REV_" forms,
# because the exact serial-tail comparison does the actual disambiguation.
USB_VID_PID_PREFIX_PATTERN = re.compile(
    r"^USB\\VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})", re.IGNORECASE
)


class WindowsPrinterBackend(PrinterBackend):
    """Windows printer backend using win32print/win32ui."""

    def get_available_printers(self) -> list[str]:
        """Get strict-match USB label printers currently present on Windows.

        A queue is kept only when its trailing USB identifier resolves to a
        connected device. Naming a queue after the printer's serial number
        rather than its VID:PID is what lets two units of the same model be
        told apart, since VID:PID is identical across a model.
        """
        printers = self._get_installed_printers()
        if not printers:
            return []

        try:
            device_ids = self.get_present_usb_device_ids()
        except ImportError:
            logger.warning("WMI not available for Windows USB printer filtering")
            return []
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(
                "Windows USB printer filtering failed during device enumeration",
                exc_info=True,
            )
            return []

        return [
            printer_name
            for printer_name in printers
            if self.matching_device_keys(printer_name, device_ids)
        ]

    @staticmethod
    def parse_name_identifier(
        printer_name: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Split a queue name's trailing USB identifier.

        Returns:
            ``(vid_pid, serial)`` where exactly one is set, or ``(None, None)``
            when the name carries no USB identifier. A VID:PID suffix wins over
            a serial suffix, since it is the older, unambiguous spelling.
        """
        vid_pid = NAME_VID_PID_PATTERN.search(printer_name.rstrip())
        if vid_pid:
            return f"{vid_pid.group(1).upper()}:{vid_pid.group(2).upper()}", None

        serial = NAME_SERIAL_PATTERN.search(printer_name.rstrip())
        # Require a digit so ordinary trailing words ("Front Desk Printer") are
        # not read as serial numbers.
        if serial and any(char.isdigit() for char in serial.group(1)):
            return None, serial.group(1).upper()

        return None, None

    @classmethod
    def matching_device_keys(
        cls, printer_name: str, device_ids: set[str]
    ) -> set[tuple[str, str, str]]:
        """Identify the physical devices a queue name resolves to.

        Each key is ``(vid, pid, instance_tail)``, one per physical device.

        For a serial-named queue the serial must equal the device-instance tail
        exactly; a name that merely ends in similar-looking characters cannot
        bind to an unrelated unit. For a legacy VID:PID queue only top-level
        device-instance nodes count, so one printer is not counted once per
        interface node.
        """
        vid_pid, serial = cls.parse_name_identifier(printer_name)
        if vid_pid is None and serial is None:
            return set()

        keys: set[tuple[str, str, str]] = set()
        for device_id in device_ids:
            if serial is not None:
                prefix = USB_VID_PID_PREFIX_PATTERN.match(device_id)
                tail = device_id.rsplit("\\", 1)[-1]
                if prefix and tail.upper() == serial:
                    keys.add(
                        (prefix.group(1).upper(), prefix.group(2).upper(), tail.upper())
                    )
                continue

            instance = USB_INSTANCE_PATTERN.match(device_id)
            if not instance:
                continue
            device_vid, device_pid, tail = instance.groups()
            if f"{device_vid.upper()}:{device_pid.upper()}" == vid_pid:
                keys.add((device_vid.upper(), device_pid.upper(), tail.upper()))

        return keys

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

    def print_image(self, img: Image.Image, printer_name: str) -> None:
        """Print image using win32ui."""
        try:
            import win32ui  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel
            from PIL import ImageWin  # pylint: disable=import-outside-toplevel
        except ImportError:
            self._print_fallback(img)
            return

        with self._printer_context(win32ui, printer_name) as context:
            # Auto-rotate if landscape
            if img.size[0] > img.size[1]:
                img = img.rotate(90, expand=True)

            # Calculate print position
            print_rect = self._calculate_print_rect(context, img.size)

            # Print the image
            with self._print_job(context, "Shipping Label"):
                dib = ImageWin.Dib(img)
                dib.draw(context.GetHandleOutput(), print_rect)

    @staticmethod
    @contextlib.contextmanager
    def _printer_context(win32ui, printer_name: str) -> Iterator:
        """Yield a device context bound to a queue, releasing it afterwards.

        The context is acquired before the try whose finally releases it: if
        CreateDC itself fails there is nothing to release, and running the
        finally anyway would raise UnboundLocalError over the real error.
        Opening the queue then happens inside that try, so a queue that cannot
        be opened no longer leaks the device context it was handed.

        Both open failures are reported as RuntimeError, the failure this
        backend documents, with the GDI error kept as ``__cause__``. A body
        failure propagates unwrapped: it is not an open failure.
        """
        try:
            context = win32ui.CreateDC()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise RuntimeError(
                f"Could not create a printer device context ({exc})."
            ) from exc

        try:
            # Opening the queue is the failure discovery cannot predict: a
            # matching USB device can be present and working while the queue
            # itself is paused, offline, or backed by a broken driver. Point
            # the operator at the tool that reports those states rather than
            # handing them a raw GDI error.
            try:
                context.CreatePrinterDC(printer_name)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                raise RuntimeError(
                    f"Could not open printer queue {printer_name!r} ({exc}). "
                    f"The printer is plugged in, but Windows could not open its "
                    f"queue - check that it is not paused or offline, and run "
                    f"diagnose-printers for details."
                ) from exc

            yield context

        finally:
            context.DeleteDC()

    @staticmethod
    @contextlib.contextmanager
    def _print_job(context, name: str) -> Iterator[None]:
        """Open a print job on a device context and close it on the way out.

        Each cleanup is guarded by its own acquisition, because GDI rejects
        EndPage without StartPage and EndDoc without StartDoc. Calling them
        unconditionally would turn a StartDoc failure ("spooler unavailable")
        into a misleading "EndPage without StartPage" and lose the real cause;
        leaving them out entirely, as this did before, abandoned an open
        document in the spooler whenever drawing the label raised.
        """
        context.StartDoc(name)
        try:
            context.StartPage()
            try:
                yield

            finally:
                context.EndPage()
        finally:
            context.EndDoc()

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

    @staticmethod
    def _get_installed_printers() -> list[str]:
        """Enumerate installed Windows printers from the spooler."""
        try:
            import win32print  # type: ignore[import-untyped] # pylint: disable=import-outside-toplevel

            printer_info = win32print.EnumPrinters(
                win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            )
            return [printer[2] for printer in printer_info]
        except ImportError:
            logger.debug("win32print not available")
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Windows printer enumeration failed", exc_info=True)
        return []

    def get_present_usb_device_ids(self, conn=None) -> set[str]:
        """Return device-instance IDs for present, working USB devices.

        The full instance ID is kept rather than just VID:PID, because the
        trailing segment carries the per-unit serial used to disambiguate two
        printers of the same model.

        Args:
            conn: An open WMI connection to reuse. One is opened when omitted.
                ``diagnose-printers`` passes its own so the report is filtered
                by this method rather than by a copy of it that can drift.
        """
        if conn is None:
            import wmi  # type: ignore[import-not-found] # pylint: disable=import-outside-toplevel,import-error

            conn = wmi.WMI()

        device_ids: set[str] = set()
        for entity in conn.Win32_PnPEntity():
            device_id = getattr(entity, "DeviceID", "") or ""
            if not device_id.upper().startswith("USB"):
                continue

            status = (getattr(entity, "Status", "") or "").lower()
            # Keep degraded printers visible so volunteers can still pick a connected
            # device that may only need paper or another local intervention.
            if status and status not in {"ok", "degraded"}:
                continue

            error_code = getattr(entity, "ConfigManagerErrorCode", 0)
            if error_code not in (None, 0):
                continue

            device_ids.add(device_id)
        return device_ids
