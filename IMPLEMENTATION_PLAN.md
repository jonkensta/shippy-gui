# Shippy GUI Implementation Plan

## Overview
Convert the shippy CLI application to a PySide6 GUI while preserving all core functionality. The GUI will feature a single-window tabbed interface with immediate printing workflow and integrated settings management.

## User Preferences
- **Layout**: Single window with two tabs: Shipping (merged Individual + Manual) and Bulk
- **Workflow**: Immediate printing (no queue, similar to CLI behavior)
- **Configuration**: Settings dialog in GUI that saves to config.ini
- **Printing**: Printer selection dropdown
- **Shipping Tab Design**: Unified interface with optional lookup helpers (inmate lookup OR Google Maps search) that populate editable address fields

## Project Structure

```
shippy-gui/
├── pyproject.toml              # uv project configuration
├── config.ini                  # Shared config with shippy CLI
├── shippy_gui/
│   ├── __init__.py
│   ├── __main__.py            # Entry point
│   ├── main_window.py         # QMainWindow with tabs
│   ├── settings_dialog.py     # Settings/preferences dialog
│   ├── tabs/
│   │   ├── __init__.py
│   │   ├── bulk_tab.py        # Bulk shipping mode
│   │   └── shipping_tab.py    # Unified shipping (inmate lookup + manual address)
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── status_widget.py   # Color-coded status messages
│   │   └── autocomplete.py    # Qt autocomplete widgets
│   ├── printing/
│   │   ├── __init__.py
│   │   ├── printer_manager.py # Printer detection & selection
│   │   ├── linux.py           # Linux printing
│   │   └── windows.py         # Windows printing
│   ├── core/
│   │   ├── __init__.py
│   │   ├── server.py          # IBP API client (reused from shippy)
│   │   ├── shipping.py        # EasyPost wrapper (reused from shippy)
│   │   ├── addresses.py       # Google Maps parser (reused from shippy)
│   │   └── models.py          # Pydantic config models (reused from shippy)
│   └── assets/
│       └── logo.jpg           # IBP logo (copied from shippy)
```

## Critical Files to Reference

### From shippy (to reuse/adapt):
- `/home/jstarr/Source/ibp/shippy/shippy/server.py` - IBP API client (reuse as-is)
- `/home/jstarr/Source/ibp/shippy/shippy/shipping.py` - EasyPost wrapper (reuse as-is)
- `/home/jstarr/Source/ibp/shippy/shippy/addresses.py` - Google Maps parser (reuse as-is)
- `/home/jstarr/Source/ibp/shippy/shippy/models.py` - Config models (reuse as-is)
- `/home/jstarr/Source/ibp/shippy/shippy/autocompletion.py` - Adapt to Qt QCompleter
- `/home/jstarr/Source/ibp/shippy/shippy/cli.py` - Reference for workflow logic
- `/home/jstarr/Source/ibp/shippy/shippy/printing/` - Adapt for GUI printing
- `/home/jstarr/Source/ibp/shippy/shippy/assets/logo.jpg` - Copy to new project

### From backend (for API understanding):
- `/home/jstarr/Source/ibp/backend/ibp/schemas.py` - API response schemas

## Implementation Phases

### Phase 1: Project Setup
**Goal**: Create project scaffold with uv and dependencies

1. Create `shippy-gui/` directory
2. Initialize uv project with `pyproject.toml`
3. Add dependencies:
   - PySide6 >= 6.8.0
   - easypost >= 10.3.0
   - pillow >= 12.0.0
   - requests >= 2.32.5
   - googlemaps >= 4.10.0
   - pydantic >= 2.12.5
   - pywin32 >= 310 (Windows only, optional)
   - WMI >= 1.5.1 (Windows only, optional)
4. Create directory structure
5. Copy reusable modules from shippy:
   - `core/server.py` (from shippy/server.py)
   - `core/shipping.py` (from shippy/shipping.py)
   - `core/addresses.py` (from shippy/addresses.py)
   - `core/models.py` (from shippy/models.py)
   - `assets/logo.jpg` (from shippy/assets/logo.jpg)

### Phase 2: Main Window & Tab Infrastructure
**Goal**: Create the main window shell and tab system

**File**: `shippy_gui/main_window.py`

Components:
- `QMainWindow` as main container
- `QTabWidget` with two tabs: "Shipping" (unified), "Bulk"
- Menu bar with:
  - File → Settings (opens settings dialog)
  - File → Quit
- Status bar for feedback messages
- Welcome/logo area (optional)

Tab management:
- Each tab is a separate widget class
- Tabs are always visible (no dynamic hiding)
- Shipping tab handles both inmate lookup and manual address entry
- Bulk tab handles unit-based bulk shipping

### Phase 3: Settings Dialog
**Goal**: GUI for editing configuration

**File**: `shippy_gui/settings_dialog.py`

Components:
- `QDialog` with form layout
- Four sections (using `QGroupBox`):
  1. **IBP Server**:
     - URL field (QLineEdit)
  2. **EasyPost API**:
     - API Key field (QLineEdit, password mode)
  3. **Google Maps API**:
     - API Key field (QLineEdit, password mode)
  4. **Return Address**:
     - Name, Street 1, Street 2, City, State, ZIP (QLineEdit)
- Buttons: Save, Cancel
- Validation using Pydantic models on Save
- Read from/write to `config.ini` using configparser

Behavior:
- Opens centered on main window
- Modal dialog
- Validates on Save, shows error dialog if invalid
- Main window reloads config after successful save

### Phase 4: Unified Shipping Tab (Inmate Lookup + Manual Address)
**Goal**: Implement unified shipping interface with optional lookup helpers

**File**: `shippy_gui/tabs/shipping_tab.py`

Layout:
```
┌─ Shipping ─────────────────────────────────────┐
│                                                 │
│ Quick Lookup (optional):                       │
│                                                 │
│ Inmate Lookup:                                 │
│ [Barcode/ID/Request          ] [Lookup]        │
│                                                 │
│ - OR -                                          │
│                                                 │
│ Address Search:                                │
│ [Google Maps autocomplete    ] [Search]        │
│                                                 │
│ ─────────────────────────────────────────────  │
│                                                 │
│ Recipient Address:                             │
│ Name:     [_____________________________]      │
│ Company:  [_____________________________]      │
│ Street 1: [_____________________________]      │
│ Street 2: [_____________________________]      │
│ City:     [_____________________________]      │
│ State:    [_____________________________]      │
│ ZIP:      [_____________________________]      │
│                                                 │
│ Weight (lbs): [___]                            │
│ Printer:      [Printer Name            ▼]     │
│                                                 │
│            [  Create Label  ]                  │
│                                                 │
│ Status: Ready                                  │
└─────────────────────────────────────────────────┘
```

**Components:**

1. **Inmate Lookup Section:**
   - QLineEdit for barcode/ID/request ID input
   - QPushButton "Lookup" to trigger search
   - Calls `server.find_inmate(user_input)`
   - On success: Populates Name (from inmate) and Address fields (from unit)
   - On multiple matches: Shows QDialog with list format: "Jurisdiction - Name (ID) - Unit Name"

2. **Address Search Section:**
   - QLineEdit with Google Maps autocomplete (adapted from shippy/autocompletion.py)
   - QPushButton "Search" or auto-search on selection
   - Debounced API calls (2 second delay)
   - On selection: Parses address and populates address fields
   - On multiple matches: Shows QDialog with address suggestions

3. **Recipient Address Fields:**
   - All fields are editable QLineEdit widgets
   - Can be populated by lookups OR manually entered/modified
   - Name, Company (optional), Street 1, Street 2 (optional), City, State, ZIP

4. **Shipment Controls:**
   - Weight QSpinBox (1-70 lbs)
   - Printer QComboBox
   - "Create Label" QPushButton
   - Status QLabel with color coding

**Workflow:**
1. User EITHER:
   - Uses inmate lookup → fills name + address fields
   - Uses Google Maps search → fills address fields only
   - Manually enters all fields
   - Or any combination (lookup then modify)
2. User verifies/edits address fields as needed
3. User enters weight
4. User clicks "Create Label"
5. **Async operation** (using QThread):
   - Show "Purchasing postage..." status
   - Call `shipping.build_shipment()` with address from fields
   - Show "Downloading label..." status
   - Download PNG and add logo
   - Show "Printing..." status
   - Print to selected printer
6. Show success/error status with color coding
7. Clear all fields for next shipment

**Error handling:**
- Network errors → show error dialog, keep inputs
- Invalid address → show warning in status bar
- Print failure → automatic refund, show error dialog

### Phase 5: Google Maps Autocomplete Widget
**Goal**: Create reusable autocomplete widget for address search

**File**: `shippy_gui/widgets/autocomplete.py`

Create custom `QCompleter` subclass:
- Adapts `shippy/autocompletion.py` GoogleMapsCompleter
- Uses `QStringListModel` for suggestions
- Debounced API calls (2 second delay)
- Thread-safe updates with QThread
- Shows "Searching..." while loading
- Integrates with QLineEdit in shipping tab

### Phase 6: Bulk Shipping Tab (Unit Autocomplete)
**Goal**: Implement bulk unit shipping

**File**: `shippy_gui/tabs/bulk_tab.py`

Layout:
```
┌─ Bulk Shipping ───────────────────────────┐
│                                            │
│ Prison Unit Name:                          │
│ [_______________________________________ ] │
│   ↓ GATESVILLE                             │ <- Autocomplete dropdown
│   ↓ HUNTSVILLE                             │
│                                            │
│ Weight (pounds):                           │
│ [_______________________________________]  │
│                                            │
│ Printer:                                   │
│ [Dropdown with available printers      ▼] │
│                                            │
│              [  Create Label  ]            │
│                                            │
│ Status: Ready                              │
└────────────────────────────────────────────┘
```

Initialization:
- On tab first shown, fetch unit list from `/units` endpoint
- Filter to Texas jurisdiction only
- Populate QCompleter with unit names
- Cache unit data for address lookup

Workflow:
1. User types unit name → autocomplete suggestions
2. User selects unit (case-insensitive match)
3. User enters weight (QSpinBox)
4. User clicks "Create Label"
5. **Async operation**:
   - Fetch unit address via `server.unit_address()`
   - Create "ATTN: Mailroom Staff" recipient
   - Build and print shipment
6. Clear fields for next shipment

### Phase 7: Printing Integration
**Goal**: Platform-specific printing with printer selection

**File**: `shippy_gui/printing/printer_manager.py`

Functions:
- `get_available_printers() -> list[str]`: Platform-specific printer discovery
- `print_image(image: PIL.Image, printer_name: str)`: Print to specific printer

**Linux Implementation** (`printing/linux.py`):
- Use CUPS API via `pycups` (new dependency)
- Or fallback to `lp -d printer_name tempfile.png`
- List printers: `lpstat -p -d` or pycups
- Default printer selection

**Windows Implementation** (`printing/windows.py`):
- Reuse existing `shippy/printing/windows.py` logic
- Adapt to accept printer_name parameter
- Printer selection via WMI or win32print enumeration
- Maintain auto-rotation and scaling

**Printer Selection Widget**:
- QComboBox populated on startup
- Refresh button to reload printer list
- Save last-used printer in QSettings
- Auto-select default printer if available

**Refund on Error**:
- Maintain existing context manager pattern
- Show error dialog with refund confirmation
- Log errors for debugging

### Phase 8: Status Feedback & Error Handling
**Goal**: User feedback system matching CLI experience

**File**: `shippy_gui/widgets/status_widget.py`

Components:
- Custom QLabel or QStatusBar widget
- Color-coded messages:
  - Green (success): "Label printed successfully!"
  - Yellow (warning): "Address verification failed - proceeding anyway"
  - Red (error): "Network error: Could not reach IBP server"
  - Blue (info): "Looking up inmate..."
- Message auto-clear after 5 seconds (configurable)
- Optional message history panel

Error Dialog Strategy:
- Non-blocking warnings: Show in status bar only
- Blocking errors: QMessageBox with details
- Network timeouts: Retry option in dialog
- Validation errors: Inline field highlighting + status message

Progress Indicators:
- QProgressDialog for long operations (> 2 seconds)
- Indeterminate progress bar during API calls
- "Cancel" button for network operations

## Technical Architecture Decisions

### Async Operations with Qt
Use `QThread` for network/API calls to prevent UI freezing:

```python
class ShipmentWorker(QThread):
    finished = Signal(dict)  # Success signal with inmate data
    error = Signal(str)      # Error signal with message
    progress = Signal(str)   # Progress updates

    def run(self):
        try:
            self.progress.emit("Looking up inmate...")
            inmate = self.server.find_inmate(self.user_input)

            self.progress.emit("Purchasing postage...")
            shipment = shipping.build_shipment(...)

            self.progress.emit("Downloading label...")
            # ... etc

            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
```

### Configuration Management
- Read config.ini on startup using existing Pydantic models
- Settings dialog writes to config.ini using configparser
- Emit signal when config changes to reload in tabs
- Validate before saving using `Config.model_validate()`

### Code Reuse Strategy
**Reuse directly** (no changes):
- `server.py` - IBP API client
- `shipping.py` - EasyPost wrapper
- `addresses.py` - Google Maps parser
- `models.py` - Pydantic config models

**Adapt for Qt**:
- `autocompletion.py` → Qt QCompleter with QStringListModel
- `console.py` → Replace with Qt widgets (QLineEdit, QSpinBox, etc.)
- `printing/` → Add printer selection, adapt platform code

**New Qt-specific code**:
- Main window, tabs, dialogs
- Signal/slot connections
- Status feedback system
- Async workers

### Dependency Management with uv
`pyproject.toml` structure:
```toml
[project]
name = "shippy-gui"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "PySide6>=6.8.0",
    "easypost>=10.3.0",
    "pillow>=12.0.0",
    "requests>=2.32.5",
    "googlemaps>=4.10.0",
    "pydantic>=2.12.5",
]

[project.optional-dependencies]
windows = [
    "pywin32>=310",
    "WMI>=1.5.1",
]
linux = [
    "pycups>=2.0.4",
]

[project.scripts]
shippy-gui = "shippy_gui.__main__:main"
```

Installation:
- `uv sync` - Install core dependencies
- `uv sync --extra windows` - Add Windows printing
- `uv sync --extra linux` - Add Linux CUPS printing

## Testing Strategy
- Manual testing for each shipping mode
- Test with real config.ini and IBP backend
- Test printer selection and printing on target platforms
- Error scenarios: network failures, invalid inputs, print failures
- Verify refund-on-error works correctly

## Future Enhancements (Out of Scope)
- Label preview before printing
- Queue-based workflow (batch multiple before printing)
- Save labels as PDF/PNG
- Shipment history/log
- Dark mode theme
- Keyboard shortcuts
- Barcode scanner integration

## Migration Path
- shippy CLI remains available for users who prefer it
- shippy-gui shares same config.ini format
- Both can coexist on same system
- Users can switch between CLI and GUI at will
