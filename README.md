# shippy-gui

`shippy-gui` is a PySide6 GUI application designed to streamline the process of printing shipping labels for books destined for incarcerated individuals in Texas. It integrates with the EasyPost API for postage purchasing and label generation, and uses Google Maps for address autocomplete.

## Purpose

The primary goal of this application is to provide an intuitive graphical interface for the Inside Books Project (IBP) to generate and print accurate shipping labels for manual address entry. It automates the postage purchasing and label creation process using EasyPost for carrier services and Google Maps for address lookup assistance.

## About Inside Books Project

Inside Books Project is an Austin-based community service volunteer organization that sends free reading materials to people incarcerated in Texas, and also publishes resource guides and short-form instructional pamphlets. Inside Books is the only books-to-prisoners program in Texas, where more than 120,000 people are behind bars. Inside Books Project works to promote reading, literacy, and education among incarcerated individuals and to educate the general public on issues of incarceration.

## Features

- **Manual Address Entry**: Single window interface for entering recipient addresses
- **Google Maps Integration**: Address autocomplete and geocoding for accurate address entry
- **EasyPost API Integration**: Utilizes the EasyPost API for purchasing postage and generating Library Mail shipping labels
- **Label Printing**: Generates and prints postage labels with IBP logo overlay when available
- **Cross-Platform Printing**: Supports Windows (win32print) and Linux (CUPS) printing via the shared [ibp-printing](https://github.com/jonkensta/ibp-printing) library
- **Settings Dialog**: GUI for configuring API keys and return address
- **Error Handling**: Labels that cannot reach a printer are saved to a print queue folder for the IBP label watcher (postage kept); automatic refund if the label itself cannot be downloaded; comprehensive error messages
- **Async Operations**: Non-blocking UI using QThread for network operations
- **Configurable Font Size**: Adjust UI font size for accessibility

## Installation

To set up the `shippy-gui` application, ensure you have Python 3.12+ and [uv](https://github.com/astral-sh/uv) installed.

### Option 1: Local Development Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/jonkensta/shippy-gui.git
    cd shippy-gui
    ```

    Printing comes from the shared `ibp-printing` library. Until it is
    published, `pyproject.toml` points at a local checkout, so clone it next to
    `shippy-gui` (i.e. at `../ibp-printing`). Running straight from git with
    `uvx` (Option 2) needs `ibp-printing` to be published first.

2.  **Create and activate a virtual environment:**

    ```bash
    uv venv
    source .venv/bin/activate
    ```

    On Windows, use `.venv\Scripts\activate`.

3.  **Install dependencies:**

    The project dependencies are defined in `pyproject.toml`. Sync them using `uv`:

    ```bash
    uv sync
    ```

    For platform-specific printing support, add the appropriate extra:

    **Linux (CUPS):** installs `pycups` (needs the libcups development
    headers; without it ibp-printing falls back to `lpstat`/`lp`)
    ```bash
    uv sync --extra linux
    ```

    **Windows (win32print):** `pywin32` and `WMI` are installed automatically on
    Windows; the extra is kept for compatibility
    ```bash
    uv sync --extra windows
    ```

### Option 2: Direct Execution with uvx

You can run the application directly from the git repository without cloning using `uvx`:

```bash
uvx --from git+https://github.com/jonkensta/shippy-gui.git@main shippy-gui
```

## Configuration

The application requires a configuration file for the EasyPost API, Google Maps API, and return address information.

### Initial Setup

On first run, the application requires a `config.ini` file in the current working directory. If it is missing, the application will create one from the packaged `config.example.ini` and exit with a configuration error so you can open Settings and fill in the required values. If it is incomplete, the application will also exit with a configuration error. Settings are always saved to `config.ini`.

### Manual Configuration

1.  Copy `config.example.ini` to `config.ini` in your working directory.
    - Note: `config.example.ini` is included in the repo for development convenience and is also bundled inside the installed package for automatic bootstrap.
2.  Populate it with your API keys and return address:

    ```ini
    [ui]
    font_size = 11
    log_file = shippy.log
    default_weight = 3

    [easypost]
    apikey = your_easypost_api_key_here

    [googlemaps]
    apikey = your_google_maps_api_key_here

    [return_address]
    name = Inside Books Project
    street1 = PO Box 301029
    street2 =
    city = Austin
    state = Texas
    zipcode = 78703
    ```

    - `ui.font_size`: UI font size in points (8-24)
    - `ui.log_file`: Log file path (relative to config directory or absolute)
    - `ui.default_weight`: Default package weight in pounds
    - `easypost.apikey`: Your EasyPost API key
    - `googlemaps.apikey`: Your Google Maps API key (for address autocomplete)
    - `return_address.*`: Your return address information (sender address for labels)

### Settings Dialog

You can also configure these settings from within the application:

1. Launch shippy-gui
2. Go to **File → Settings** (or press `Ctrl+,`)
3. Fill in the required fields
4. Click **Save**

The settings dialog validates your configuration and saves it to `config.ini`.

## Usage

### Running from Local Installation

Once you've installed the dependencies in your virtual environment, you can run the application:

```bash
python -m shippy_gui
```

Or if you installed it as a package:

```bash
shippy-gui
```

### Running with uvx

Run directly from the repository without local installation:

```bash
uvx --from git+https://github.com/jonkensta/shippy-gui.git@main shippy-gui
```

### Creating a Desktop Shortcut (Windows)

To create a Windows desktop shortcut that launches shippy-gui, you can use PowerShell:

```powershell
powershell.exe -NoExit -Command "& { & 'uvx' --from 'git+https://github.com/jonkensta/shippy-gui.git@main' 'shippy-gui' }"
```

To create the shortcut:

1. Right-click on your desktop
2. Select **New → Shortcut**
3. Paste the PowerShell command above as the location
4. Name the shortcut "Shippy GUI" (or your preferred name)
5. Click **Finish**

#### Using a `.cmd` Launcher (Recommended)

For more reliable startup and an explicit config path, create a small `.cmd` file and point a shortcut at it.

Example `shippy-gui.cmd`:

```bat
@echo off
setlocal

REM Set working directory (where your config lives)
cd /d "C:\InsideBooks\ShippyGUI"

REM Run the app
uvx --from git+https://github.com/jonkensta/shippy-gui.git@main shippy-gui
```

To create the shortcut:

1. Save the `.cmd` file in a stable location
2. Right-click on your desktop and select **New → Shortcut**
3. Browse to the `.cmd` file
4. Name the shortcut and click **Finish**

### Application Workflow

1. **Configure settings** (File → Settings) on first run
2. **Enter recipient address**:
   - Type an address in the search field and select from Google Maps autocomplete suggestions
   - Address fields auto-populate when you select a result
   - All fields are editable for manual adjustment
3. **Enter package weight** in pounds (1-70 range)
4. **Select printer** from the dropdown
5. **Click "Create Label"**:
   - Application purchases postage via EasyPost (Library Mail rate)
   - Downloads label from EasyPost and overlays IBP logo from `assets/logo.jpg` when available
   - Prints to selected printer
   - Shows tracking number on success
   - If no printer can take the label, saves it to `Downloads\to-print\` to print later (postage is **not** refunded; see [Label did not print](#label-did-not-print))
   - Automatically refunds if the label cannot be downloaded or prepared

## Platform Support

Printer discovery and direct printing are provided by `ibp-printing`:

- **Windows**: Uses win32print. Only USB label printers are listed: the print
  queue name must end with the printer's USB ID (e.g. `Zebra 20d1:7008`,
  `Zebra_20d1:7008` or `Zebra-20d1:7008`) and that USB device must be plugged
  in. Printers whose USB device or queue reports a problem are still listed,
  just lower down.
- **Linux**: Uses CUPS via `lp`; every CUPS queue is listed.

Shift + Click on "Create Label" uses the Qt system print dialog instead.
Canceling that dialog refunds the postage. If printing cannot even start, the
label is saved to `Downloads\to-print\` like any other label no printer took;
if it fails after printing started, you get the "Check The Printer" warning and
nothing is refunded.

### Printer logs

Every discovery and print attempt is logged in detail by `ibp-printing` to
`printer-shippy-gui.log` (human readable) and `printer-shippy-gui.jsonl` (one JSON object per line)
in `%LOCALAPPDATA%\ibp-printing\logs` on Windows
(`~/.local/state/ibp-printing/logs` on Linux). Printer messages at INFO and
above also appear in the shippy-gui log file.

## Keyboard Shortcuts

- `Ctrl+,` - Open Settings dialog
- `Ctrl+Q` - Quit application

## Troubleshooting

### "Configuration Error" on startup
- Ensure `config.ini` exists and is properly formatted
- Use File → Settings to validate and save your configuration

### "Failed to verify address" warning
- This is non-blocking; you can proceed with shipment
- Double-check the address manually before shipping

### Label did not print
If the label cannot be sent to any printer, the postage is **kept** (not
refunded) and the label, with the IBP logo, is saved to the print queue folder
`Downloads\to-print\`. The "Label Did Not Print" dialog shows the exact file.

- If the IBP label watcher (from ibp-printing) is running, the label prints
  automatically as soon as a label printer is working - plug in or fix the
  printer and wait.
- **Before** you print that file yourself, or refund the shipment in EasyPost
  (the dialog shows its tracking number) because the package will not ship,
  delete the file from `to-print\` first, so the watcher does not print it too.
  If the file is already gone, the watcher has picked it up: check the printer
  (and the `printed\` and `check-printer\` folders) first.
- Check that your printer is online and selected correctly.

The app only refunds automatically when the label could not be downloaded or
prepared after buying postage, or when it could not even be saved to the queue.

### "Check The Printer" warning
The label reached the print queue, but the queue then reported a problem (or
it could not be confirmed that the job got there, or printing failed with an
unexpected error after the label may have been sent). The postage is **not**
refunded and the label is **not** queued again, because it may still print.
Check the printer before reprinting so you do not end up with two labels.

### Printer missing from the list
- Click **Refresh** after plugging in or turning on the printer
- Run `uv run diagnose-printers` to see every print queue and why it is or is not listed
- Send the `printer-shippy-gui.log`/`printer-shippy-gui.jsonl` files (see [Printer logs](#printer-logs)) when reporting a problem

### Google Maps autocomplete not working
- Verify your Google Maps API key in Settings
- Ensure Places API is enabled in your Google Cloud Console
- Check that you have sufficient API quota

## Development

This application shares core shipping logic with the [shippy CLI tool](https://github.com/jonkensta/shippy). The following modules are reused:
- `core/services.py` - EasyPost wrapper
- `core/addresses.py` - Google Maps geocoding
- `core/models.py` - Pydantic configuration models

For development setup, follow the Local Development Installation instructions above.

To enable Git hooks for linting and formatting checks:

```bash
uv run pre-commit install
```

## License

This project is developed for the Inside Books Project. For licensing information, please contact IBP directly.
