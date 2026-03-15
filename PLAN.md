# Plan: Tighten Windows Printer Dropdown to Present USB Label Printers Only

## Summary

The current printer dropdown is populated from the platform printer backend with no filtering. On Windows specifically, the code uses `win32print.EnumPrinters(PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS)` and returns every enumerated logical printer name. It does not currently restrict by:

- USB transport
- present vs disconnected device state
- label-printer type
- naming convention

The repository already includes the two Windows-side facilities needed to improve this:

- `pywin32` / `win32print`: enumerate installed logical printers and default printer
- `WMI`: inspect currently present Plug and Play / USB device identifiers

Given the chosen policy, the implementation should use a strict, fail-closed filter on Windows:

- show only printers whose configured printer name matches a currently plugged-in USB device identifier
- if no printers match, show no printers
- use a printer-name suffix in the form `...<separator>VID:PID` as the canonical matching token

This intentionally leans on the existing naming convention workaround instead of trying to infer “label printer” from driver strings alone. For this project, assume printer names end with a trailing `VID:PID` token such as `20d1:7008`, separated from the rest of the name by whitespace or a whitespace-like separator such as `_`. Example: `iDPRT_SP310_20d1:7008`.

## Current State

### Linux
- `ShipmentControls._load_printers()` calls `get_available_printers()` and loads every returned name into the combo box.
- Linux backend returns all CUPS / `lpstat` printers.

### Windows
- `PrinterService` selects `WindowsPrinterBackend` when `platform.system() == "Windows"`.
- `WindowsPrinterBackend.get_available_printers()` calls `win32print.EnumPrinters(PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS)`.
- It returns `[printer[2] for printer in printer_info]`, which is the logical printer name.
- There is no current filtering by transport, presence, or printer class.

## Decision

### Selected policy
- Windows dropdown behavior becomes `Strict Match`.
- Only printers whose name suffix matches a currently present USB device identifier are shown.
- If none match, the dropdown should show no printers and disable label creation exactly as it already does for “No printers found”.

### Selected identifier
- Use the USB `VID:PID` pair as the match source.
- Match against the trailing printer-name suffix in the form `...<separator>VID:PID`.
- Derive `VID:PID` from the currently present Windows USB PnP device identifiers.
- Do not use the full PnP device identifier as the visible printer-name suffix.
- Do not use `USB001`-style port names as the primary key.

## Available Facilities to Use

### 1. Logical printer enumeration
Use the existing `win32print` path to enumerate logical printers:
- source of truth for installed/usable Windows printer names
- still used to determine which printers the application can print to

### 2. Present USB device enumeration
Use Windows-side device inspection to enumerate only currently present USB printer devices:
- primary implementation facility: `WMI`
- primary WMI class: `Win32_PnPEntity`
- primary fields: `DeviceID`, `PNPClass`, `Name`, `Status`, `ConfigManagerErrorCode`
- query target: present printer-related PnP entities and their identifiers
- extraction target: `VID:PID` pairs from those identifiers
- filtering target: USB-backed printer devices only

### 3. Matching strategy
Do not attempt to derive a printer/device relationship from Windows spooler internals in this change.
Instead:
- trust the logical printer name from `EnumPrinters`
- trust the plugged-in USB `VID:PID` set derived from WMI
- keep only printer names that end with one of the normalized `VID:PID` suffixes

This matches the user’s established workaround and avoids brittle heuristics.

## Proposed Implementation

### 1. Add Windows-only printer filtering step
Modify `WindowsPrinterBackend.get_available_printers()` to:

1. enumerate all logical printers with `EnumPrinters(...)`
2. query the set of currently present USB printer `VID:PID` values
3. normalize both:
   - logical printer names
   - USB `VID:PID` values
4. retain only printers whose name ends with one of the normalized `VID:PID` suffixes
5. return the filtered list

Behavior:
- on success: only matching printers are returned
- if no matches: return `[]`
- if USB-device enumeration itself fails unexpectedly:
  - log the failure
  - return `[]` rather than the broad printer list, because policy is strict/fail-closed

### 2. Introduce identifier normalization helpers
Add Windows-backend-local helper functions to normalize identifiers.

Normalization rules:
- for `VID:PID` identifiers, normalization is simple: uppercase and strip surrounding whitespace
- for printer-name suffix matching, treat whitespace and whitespace-like separators used in printer names, including `_`, as equivalent suffix boundaries
- do not over-normalize the extracted `VID:PID` token beyond case and trim

Recommended implementation shape:
- `_normalize_identifier(value: str) -> str`
- `_extract_vid_pid(device_id: str) -> Optional[str]`
- `_printer_name_matches_usb_id(printer_name: str, usb_id: str) -> bool`

Matching rule:
- extract a normalized `VID:PID` token from the Windows device identifier
- `_extract_vid_pid()` should parse `VID_XXXX` and `PID_YYYY` from strings such as `USB\VID_20D1&PID_7008\5&3A2D8B1E&0&1`
- extraction rule: capture the four hexadecimal digits after `VID_`, capture the four hexadecimal digits after `PID_`, lowercase them, and join them as `vid:pid`
- if either component is missing, return `None`
- match only on suffix
- require the suffix to be the final `VID:PID` token in the printer name, such as `iDPRT_SP310_20d1:7008` or `iDPRT SP310 20d1:7008`
- do not match substrings in the middle of the printer name
- if multiple USB IDs could match, treat any one match as sufficient

### 3. Query currently present USB printer identifiers
Add Windows-backend helpers such as:
- `_get_present_usb_printer_ids() -> set[str]`
- `_extract_vid_pid(device_id: str) -> Optional[str]`

Implementation sequence:
1. import `wmi`
2. query `Win32_PnPEntity` as the primary data source
3. keep entities where:
   - `PNPClass == "Printer"`
   - `DeviceID` starts with `USB`
   - `Status` indicates the device is usable or present
   - `ConfigManagerErrorCode == 0` when available
4. extract `DeviceID` values for those entities
5. extract `VID:PID` pairs from those `DeviceID` values
6. return normalized `VID:PID` strings

Recommended filtering criteria:
- only present devices
- only printer-related devices
- only USB-backed identifiers
- ignore virtual printers, network printers, PDF printers, and disconnected ghost devices

If `Win32_PnPEntity` proves inconsistent across machines, use this fallback hierarchy:
1. `Win32_PnPEntity` filtered by `PNPClass = 'Printer'` and `DeviceID LIKE 'USB%'`
2. broader `Win32_PnPEntity` query for present USB PnP entities, then narrow to printer-ish names/classes
3. only if both are insufficient, evaluate a PowerShell `Get-PnpDevice -PresentOnly` subprocess in a follow-up change

This change should not begin with PowerShell unless WMI proves inadequate.

### 4. Add a manual refresh control next to the printer dropdown
Update the shipment controls UI so the printer row includes:
- the existing printer combo box
- a new `Refresh` button immediately next to it

Layout detail:
- replace the current `QFormLayout.addRow("Printer:", self.printer_combo)` field widget with a small `QHBoxLayout` container that holds the combo box and the refresh button

Implementation behavior:
- extract the current one-time printer loading logic into a reusable refresh method
- call that refresh method during widget initialization so startup behavior stays the same
- wire the new button to call the same refresh method on demand

Refresh behavior:
1. query `get_available_printers()` again
2. clear and repopulate the combo box
3. preserve the current selection if it is still present after refresh
4. otherwise select the default printer if it is present
5. otherwise select the first available printer
6. if no printers are found, show `No printers found` and disable label creation as today

UI constraints:
- keep the button small and adjacent to the combo box
- do not require an application restart to observe printer changes
- update hover text for both controls using plain-language, volunteer-friendly instructions

Tooltip requirements:
- printer dropdown tooltip should explicitly explain that the list only shows currently connected USB label printers
- printer dropdown tooltip should explain that the printer name must end with the USB ID in `VID:PID` form
- printer dropdown tooltip should tell the user to click `Refresh` if a printer was just plugged in or turned on
- printer dropdown tooltip should tell the user what to check if no printers appear
- refresh button tooltip should explicitly say that it scans again for connected label printers
- refresh button tooltip should tell the user to use it after plugging in or turning on a printer
- tooltip wording should use full sentences and avoid terse technical shorthand so older volunteers can follow it easily

### 5. Keep default-printer selection post-filter
Leave `get_default_printer()` unchanged.
The refreshed printer-loading path should only auto-select the default printer if the current selection is gone and the default exists in the filtered list.

Result:
- default printer is selected only when it is also an allowed, currently present USB printer
- refresh preserves the user’s current selection whenever it remains valid

### 6. Keep Linux unchanged in this change set
Do not change Linux printer filtering in this task.

Reasoning:
- the user explicitly called out Windows as the more likely place for this to work
- Linux printer-device correlation is a separate problem and should not be mixed into the Windows implementation

## Important Changes to Public/Internal APIs

These are internal interfaces but should be treated as intentional contract changes:

1. `WindowsPrinterBackend.get_available_printers()`
- current: returns all Windows-enumerated logical printers
- planned: returns only printers whose names end with a `VID:PID` suffix matching a currently present USB device

2. New Windows backend helpers
- `_get_present_usb_printer_ids() -> set[str]`
- `_extract_vid_pid(device_id: str) -> Optional[str]`
- `_normalize_identifier(value: str) -> str`
- `_printer_name_matches_usb_id(printer_name: str, usb_id: str) -> bool`

No user-facing config fields or CLI/API surfaces need to change in this task.

3. `ShipmentControls` UI behavior
- current: printer list is populated once during widget initialization
- planned: printer list is populated on initialization and can be refreshed on demand with a dedicated button
- planned: printer dropdown and refresh button tooltips are rewritten in explicit plain language for older volunteers

## Data Flow

1. UI asks for available printers
2. printer manager delegates to printer service
3. printer service selects Windows backend
4. Windows backend enumerates logical printers with `win32print`
5. Windows backend queries present USB printer device IDs with `WMI`
6. Windows backend extracts `VID:PID` values from those IDs
7. Windows backend filters logical printer names using `VID:PID` suffix matching
8. filtered names are returned to the combo box
9. combo box disables shipment creation if the filtered list is empty
10. user can press `Refresh` later to rerun the same printer-discovery path without restarting the app

## Edge Cases and Failure Modes

### 1. No USB label printer connected
- filtered list is empty
- combo shows “No printers found”
- create button remains disabled

### 2. Printer installed but disconnected
- printer remains in Windows spooler enumeration
- absent from the present USB `VID:PID` set
- filtered out

### 3. Virtual printer
- appears in spooler enumeration
- has no current USB printer PnP identity
- filtered out

### 4. Network printer
- appears in spooler enumeration
- not USB-backed
- filtered out

### 5. Naming convention missing or malformed
- printer is present and installed, but its logical printer name does not end with a recognized `VID:PID` suffix separated from the rest of the name by whitespace or `_`
- filtered out by design
- this is expected strict behavior, not an error

### 6. Multiple similar printers
- if they carry distinct `VID:PID` suffixes, matching remains unambiguous
- if multiple identical devices share the same `VID:PID`, this naming convention alone will not distinguish between them, which is an accepted limitation of this plan
- this limitation should also be documented operationally for IBP setup so staff do not expect two identical connected printers to be distinguishable

### 7. WMI query fails
- log at `WARNING` level with exception details so the failure is visible in `shippy.log`
- return empty printer list on Windows
- do not silently fall back to the broad printer list

### 8. Printer is plugged in or unplugged after app startup
- current dropdown contents may be stale
- clicking `Refresh` reruns discovery and updates the list
- no restart is required

## Testing and Validation

### Unit tests
Add Windows-backend-focused tests that do not require a real Windows machine by mocking `win32print` and `wmi`:

1. `get_available_printers` returns only suffix-matching printers
2. non-matching logical printers are excluded
3. disconnected printer IDs produce an empty result
4. malformed or missing suffixes are excluded
5. virtual/network/non-USB printers are excluded when the USB ID set does not include them
6. default printer behavior remains unchanged after filtering
7. refresh preserves current selection when still valid
8. refresh falls back to default printer and then first available printer when current selection disappears
9. printer dropdown tooltip explains the filtered printer behavior and refresh guidance in plain language
10. refresh button tooltip explains when to click it in plain language
11. `_extract_vid_pid()` correctly parses `USB\VID_20D1&PID_7008\...` into `20d1:7008` and returns `None` for malformed IDs
12. WMI failure returns `[]` and emits a warning log
13. identifier normalization handles case differences and whitespace or `_` separator variations

### Manual validation on Windows
Run on a Windows machine with:
1. one USB label printer connected and correctly suffixed printer name
   - expected: printer appears
2. same printer unplugged
   - expected: printer disappears
3. regular office printer installed
   - expected: printer does not appear
4. PDF printer installed
   - expected: printer does not appear
5. multiple label printers connected
   - expected: all correctly suffixed, currently present ones appear
6. plug in a supported printer after the app is already open, then click `Refresh`
   - expected: printer appears without restarting the app
7. unplug a supported printer after the app is already open, then click `Refresh`
   - expected: printer disappears without restarting the app

## Acceptance Criteria

- On Windows, the dropdown contains only printers whose names end with a `VID:PID` suffix matching a currently present USB device.
- Installed but unplugged printers do not appear.
- Non-USB printers do not appear.
- Virtual printers do not appear.
- If no USB-ID-matched printers are present, the UI behaves as “No printers found”.
- The current Linux implementation is unchanged.
- Default-printer preselection still works when the default printer survives filtering.
- Clicking `Refresh` updates the dropdown to reflect printers plugged in or unplugged after app startup.
- Refresh preserves the current selection when that printer is still available.
- Hover text for the printer dropdown and refresh button gives explicit, plain-language guidance suitable for older volunteers.

## Assumptions and Defaults

- Assume the existing Windows naming convention can be enforced operationally: printer names are suffixed with the relevant USB `VID:PID`, with the suffix separated from the base name by whitespace or `_`, e.g. `iDPRT_SP310_20d1:7008`.
- Assume strict/fail-closed behavior is preferred over a broader fallback list.
- Assume `WMI` via `Win32_PnPEntity` is the first facility to try for present USB-device enumeration because it is already declared as a Windows dependency.
- Assume Linux filtering is out of scope for this change.
- Assume the suffix source of truth is the USB `VID:PID` pair derived from the PnP device identifier, not `USB001` and not the full raw PnP identifier.

## TODO

- [ ] Update the Windows printer backend to filter the printer list by currently present USB `VID:PID` values.
- [ ] Implement `_extract_vid_pid()` to parse `VID_XXXX` and `PID_YYYY` from Windows PnP device IDs.
- [ ] Query `Win32_PnPEntity` via `WMI` for present USB printer devices and derive the current `VID:PID` set.
- [ ] Add suffix-matching helpers that treat whitespace and `_` as equivalent printer-name separators before the trailing `VID:PID` token.
- [ ] Keep the Windows filter fail-closed and log WMI failures at `WARNING` level.
- [ ] Add a `Refresh` button next to the printer dropdown in `ShipmentControls` using a shared refresh path.
- [ ] Preserve the current printer selection on refresh when it remains valid, otherwise fall back to the default printer and then the first available printer.
- [ ] Rewrite the printer dropdown tooltip in plain language for older volunteers.
- [ ] Add a plain-language tooltip to the `Refresh` button explaining when to use it.
- [ ] Add unit tests for `VID:PID` extraction, Windows printer filtering, refresh behavior, warning logging, and tooltip text.
- [ ] Manually validate on Windows with plugged-in, unplugged, virtual, and non-USB printers.
