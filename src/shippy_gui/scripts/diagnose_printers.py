"""Diagnostic script for Windows USB printer detection.

Run this on a Windows machine to see what WMI reports about connected printers
and why a device may or may not be recognized by shippy-gui.

Usage:
    uvx --from "shippy-gui[windows] @ git+https://github.com/jonkensta/shippy-gui.git" \
        diagnose-printers
"""

# pylint: disable=import-outside-toplevel,duplicate-code

import re
import sys

VID_PID_PATTERN = re.compile(r"VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})")


def main():  # pylint: disable=too-many-locals,too-many-statements
    """Run printer diagnostics and print results to stdout."""
    if sys.platform != "win32":
        print("This script is intended for Windows only.")
        sys.exit(1)

    try:
        import win32print  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: win32print not available. Install with: uv sync --extra windows")
        sys.exit(1)

    try:
        import wmi  # type: ignore[import-not-found]
    except ImportError:
        print("ERROR: WMI not available. Install with: uv sync --extra windows")
        sys.exit(1)

    _print_installed_printers(win32print)
    conn = wmi.WMI()
    _print_wmi_printer_entities(conn)
    _print_wmi_usb_entities(conn)
    _print_matching_results(win32print, conn)


def _print_installed_printers(win32print) -> None:
    """Print all printers registered with the Windows spooler."""
    print("=" * 60)
    print("INSTALLED PRINTERS (win32print)")
    print("=" * 60)
    printer_info = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )
    installed_names = [p[2] for p in printer_info]
    for name in installed_names:
        print(f"  {name!r}")
    if not installed_names:
        print("  (none)")
    print()
    default = win32print.GetDefaultPrinter() if installed_names else None
    print(f"Default printer: {default!r}")
    print()


def _print_wmi_printer_entities(conn) -> None:
    """Print all WMI PnP entities with PNPClass='Printer'."""
    print("=" * 60)
    print("ALL WMI PnP ENTITIES WITH CLASS 'Printer'")
    print("=" * 60)
    printer_entities = [
        e for e in conn.Win32_PnPEntity() if getattr(e, "PNPClass", None) == "Printer"
    ]
    if printer_entities:
        for entity in printer_entities:
            device_id = getattr(entity, "DeviceID", "") or ""
            status = getattr(entity, "Status", "") or ""
            error_code = getattr(entity, "ConfigManagerErrorCode", None)
            name = getattr(entity, "Name", "") or ""
            vid_pid = _extract_vid_pid(device_id)
            print(f"  Name:          {name!r}")
            print(f"  DeviceID:      {device_id!r}")
            print(f"  Status:        {status!r}")
            print(f"  ErrorCode:     {error_code!r}")
            print(f"  StartsWithUSB: {device_id.startswith('USB')}")
            print(f"  VID:PID:       {vid_pid!r}")
            print()
    else:
        print("  (none found with PNPClass='Printer')")
    print()


def _print_wmi_usb_entities(conn) -> None:
    """Print all USB PnP entities that have a detectable VID:PID."""
    print("=" * 60)
    print("ALL WMI USB PnP ENTITIES WITH A VID:PID")
    print("=" * 60)
    for entity in conn.Win32_PnPEntity():
        device_id = getattr(entity, "DeviceID", "") or ""
        if not device_id.startswith("USB"):
            continue
        vid_pid = _extract_vid_pid(device_id)
        if not vid_pid:
            continue
        pnp_class = getattr(entity, "PNPClass", "") or ""
        status = getattr(entity, "Status", "") or ""
        error_code = getattr(entity, "ConfigManagerErrorCode", None)
        name = getattr(entity, "Name", "") or ""
        print(f"  Name:      {name!r}")
        print(f"  DeviceID:  {device_id!r}")
        print(f"  PNPClass:  {pnp_class!r}")
        print(f"  Status:    {status!r}")
        print(f"  ErrorCode: {error_code!r}")
        print(f"  VID:PID:   {vid_pid!r}")
        print()
    print()


def _print_matching_results(win32print, conn) -> None:
    """Print the final shippy-gui matching verdict for each installed printer."""
    print("=" * 60)
    print("SHIPPY-GUI MATCHING RESULTS")
    print("=" * 60)
    usb_ids = _get_present_usb_printer_ids(conn)
    print(f"USB printer VID:PIDs seen by shippy-gui: {usb_ids or '(none)'}")
    print()
    printer_info = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    )
    for name in [p[2] for p in printer_info]:
        matched = any(_printer_name_matches_usb_id(name, uid) for uid in usb_ids)
        verdict = "MATCH (would appear in dropdown)" if matched else "no match"
        print(f"  {name!r} -> {verdict}")


def _extract_vid_pid(device_id: str):
    """Extract and normalize VID:PID from a Windows device ID string."""
    match = VID_PID_PATTERN.search(device_id)
    if not match:
        return None
    vid, pid = match.groups()
    return f"{vid.upper()}:{pid.upper()}"


def _get_present_usb_printer_ids(conn) -> set[str]:
    """Return VID:PID values for USB printers that pass shippy-gui's WMI filters."""
    usb_ids: set[str] = set()
    for entity in conn.Win32_PnPEntity():
        device_id = getattr(entity, "DeviceID", "") or ""
        if not device_id.startswith("USB"):
            continue
        status = (getattr(entity, "Status", "") or "").lower()
        if status and status not in {"ok", "degraded"}:
            continue
        error_code = getattr(entity, "ConfigManagerErrorCode", 0)
        if error_code not in (None, 0):
            continue
        vid_pid = _extract_vid_pid(device_id)
        if vid_pid:
            usb_ids.add(vid_pid.upper())
    return usb_ids


def _printer_name_matches_usb_id(printer_name: str, usb_id: str) -> bool:
    """Return True when printer name ends with the expected VID:PID suffix."""
    normalized = printer_name.rstrip().upper()
    normalized_id = usb_id.strip().upper()
    if not normalized.endswith(normalized_id):
        return False
    boundary_index = len(normalized) - len(normalized_id)
    if boundary_index == 0:
        return True
    return normalized[boundary_index - 1] in {" ", "\t", "_"}


if __name__ == "__main__":
    main()
