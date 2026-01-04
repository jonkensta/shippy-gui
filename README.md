# shippy-gui

`shippy-gui` is a PySide6 GUI application designed to streamline the process of printing shipping labels for books destined for incarcerated individuals in Texas. It integrates with an internal server for address management and the EasyPost API for postage purchasing and label generation.

## Purpose

The primary goal of this application is to provide an intuitive graphical interface for the Inside Books Project (IBP) to generate and print accurate shipping labels. It automates the postage purchasing and label creation process, interacting with IBP's internal server to retrieve recipient addresses and using EasyPost for carrier services. The application provides a unified shipping interface with multiple lookup helpers for different workflows.

## About Inside Books Project

Inside Books Project is an Austin-based community service volunteer organization that sends free reading materials to people incarcerated in Texas, and also publishes resource guides and short-form instructional pamphlets. Inside Books is the only books-to-prisoners program in Texas, where more than 120,000 people are behind bars. Inside Books Project works to promote reading, literacy, and education among incarcerated individuals and to educate the general public on issues of incarceration.

## Features

- **Unified Shipping Interface**: Single window with three lookup helpers for different workflows
  - **Inmate Lookup**: Find inmate by barcode, ID, or request number
  - **Address Search**: Google Maps autocomplete for manual address entry
  - **Unit Lookup**: Select prison unit and auto-fill mailroom address
- **Integration with IBP Server**: Fetches unit addresses and inmate information from an internal IBP server
- **EasyPost API Integration**: Utilizes the EasyPost API for purchasing postage and generating Library Mail shipping labels
- **Google Maps Integration**: Address autocomplete and geocoding for accurate address entry
- **Label Printing**: Generates and prints postage labels with optional custom logo overlay
- **Cross-Platform Printing**: Supports Windows (win32print) and Linux (CUPS) printing
- **Settings Dialog**: GUI for configuring API keys, server URL, and return address
- **Error Handling**: Automatic refund on print failure, comprehensive error messages with tooltips
- **Async Operations**: Non-blocking UI using QThread for network operations

## Installation

To set up the `shippy-gui` application, ensure you have Python 3.12+ and [uv](https://github.com/astral-sh/uv) installed.

### Option 1: Local Development Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/jonkensta/shippy-gui.git
    cd shippy-gui
    ```

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

    **Linux (CUPS):**
    ```bash
    uv sync --extra linux
    ```

    **Windows (win32print):**
    ```bash
    uv sync --extra windows
    ```

### Option 2: Direct Execution with uvx

You can run the application directly from the git repository without cloning using `uvx`:

```bash
uvx --from git+https://github.com/jonkensta/shippy-gui.git@main shippy-gui
```

## Configuration

The application requires a configuration file for the IBP server, EasyPost API, Google Maps API, and return address information.

### Initial Setup

On first run, the application will look for `config.ini` in the current working directory. If not found, you can create it manually or use the Settings dialog (File → Settings) from within the application.

### Manual Configuration

1.  Create a `config.ini` file in your working directory (or specify a custom path).
2.  Populate it with your API keys, server URL, and return address:

    ```ini
    [ibp]
    url = http://your_ibp_server_url:8000

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

    - `ibp.url`: The URL of your internal IBP server
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

To specify a custom config file location:

```bash
python -m shippy_gui --config /path/to/your/config.ini
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

For a shortcut with a specific config file:

```powershell
powershell.exe -NoExit -Command "& { & 'uvx' --from 'git+https://github.com/jonkensta/shippy-gui.git@main' 'shippy-gui' --config 'C:\path\to\your\config.ini' }"
```

To create the shortcut:

1. Right-click on your desktop
2. Select **New → Shortcut**
3. Paste one of the PowerShell commands above as the location
4. Name the shortcut "Shippy GUI" (or your preferred name)
5. Click **Finish**

### Application Workflow

1. **Configure settings** (File → Settings) on first run
2. **Choose a lookup method**:
   - **Inmate Lookup**: Enter barcode (TEX-12345678-0), inmate ID (12345678), or request ID
   - **Address Search**: Type an address and select from Google Maps autocomplete suggestions, then click Load
   - **Unit Lookup**: Type a prison unit name and select from autocomplete, then click Load
3. **Verify/edit** the recipient address fields (all fields are editable)
4. **Enter package weight** in pounds (1-70 range)
5. **Select printer** from the dropdown
6. **Click "Create Label"**:
   - Application purchases postage via EasyPost
   - Downloads and optionally adds logo to label
   - Prints to selected printer
   - Shows tracking number on success
   - Automatically refunds if printing fails

## Platform Support

- **Windows**: Uses win32print for printing (requires `--extra windows` during installation)
- **Linux**: Uses CUPS for printing via `lp` command (requires `--extra linux` during installation)

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

### Print failure with refund
- Check that your printer is online and selected correctly
- Verify printer name matches exactly (case-sensitive on some systems)
- The shipment is automatically refunded if printing fails

### Google Maps autocomplete not working
- Verify your Google Maps API key in Settings
- Ensure Places API is enabled in your Google Cloud Console
- Check that you have sufficient API quota

## Development

This application shares core shipping logic with the [shippy CLI tool](https://github.com/jonkensta/shippy). The following modules are reused:
- `core/server.py` - IBP API client
- `core/shipping.py` - EasyPost wrapper
- `core/addresses.py` - Google Maps parser
- `core/models.py` - Pydantic configuration models

For development setup, follow the Local Development Installation instructions above.

## License

This project is developed for the Inside Books Project. For licensing information, please contact IBP directly.
