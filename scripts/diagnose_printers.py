"""Diagnostic script for Windows USB printer detection.

Run this on a Windows machine to see what WMI reports about connected printers
and why a device may or may not be recognized by shippy-gui.

Usage:
    uvx --from "shippy-gui[windows] @ git+https://github.com/jonkensta/shippy-gui.git" \
        python scripts/diagnose_printers.py
"""

import re
import sys

VID_PID_PATTERN = re.compile(r"VID_([0-9A-Fa-f]{4}).*PID_([0-9A-Fa-f]{4})")


def main():
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
    print("=" * 60)
    print("ALL WMI PnP ENTITIES WITH CLASS 'Printer'")
    print("=" * 60)
    conn = wmi.WMI()
    printer_entities = [
        e for e in conn.Win32_PnPEntity()
        if getattr(e, "PNPClass", None) == "Printer"
    ]
    if printer_entities:
        for entity in printer_entities:
            device_id = getattr(entity, "DeviceID", "") or ""
            status = getattr(entity, "Status", "") or ""
            error_code = getattr(entity, "ConfigManagerErrorCode", None)
            name = getattr(entity, "Name", "") or ""
            print(f"  Name:          {name!r}")
            print(f"  DeviceID:      {device_id!r}")
            print(f"  Status:        {status!r}")
            print(f"  ErrorCode:     {error_code!r}")
            print(f"  StartsWithUSB: {device_id.startswith('USB')}")
            vid_pid = _extract_vid_pid(device_id)
            print(f"  VID:PID:       {vid_pid!r}")
            print()
    else:
        print("  (none found with PNPClass='Printer')")

    print()
    print("=" * 60)
    print("ALL WMI USB PnP ENTITIES (any class, DeviceID starts with USB)")
    print("=" * 60)
    usb_entities = [
        e for e in conn.Win32_PnPEntity()
        if (getattr(e, "DeviceID", "") or "").startswith("USB")
    ]
    for entity in usb_entities:
        device_id = getattr(entity, "DeviceID", "") or ""
        pnp_class = getattr(entity, "PNPClass", "") or ""
        status = getattr(entity, "Status", "") or ""
        error_code = getattr(entity, "ConfigManagerErrorCode", None)
        name = getattr(entity, "Name", "") or ""
        vid_pid = _extract_vid_pid(device_id)
        if vid_pid:
            print(f"  Name:      {name!r}")
            print(f"  DeviceID:  {device_id!r}")
            print(f"  PNPClass:  {pnp_class!r}")
            print(f"  Status:    {status!r}")
            print(f"  ErrorCode: {error_code!r}")
            print(f"  VID:PID:   {vid_pid!r}")
            print()

    print()
    print("=" * 60)
    print("SHIPPY-GUI MATCHING RESULTS")
    print("=" * 60)
    usb_ids = _get_present_usb_printer_ids(conn)
    print(f"USB printer VID:PIDs seen by shippy-gui: {usb_ids or '(none)'}")
    print()
    for name in installed_names:
        matched = any(_printer_name_matches_usb_id(name, uid) for uid in usb_ids)
        print(f"  {name!r} -> {'MATCH (would appear in dropdown)' if matched else 'no match'}")


def _extract_vid_pid(device_id: str):
    match = VID_PID_PATTERN.search(device_id)
    if not match:
        return None
    vid, pid = match.groups()
    return f"{vid.upper()}:{pid.upper()}"


def _get_present_usb_printer_ids(conn) -> set[str]:
    usb_ids: set[str] = set()
    for entity in conn.Win32_PnPEntity():
        if getattr(entity, "PNPClass", None) != "Printer":
            continue
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
