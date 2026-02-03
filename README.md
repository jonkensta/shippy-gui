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
- **Cross-Platform Printing**: Supports Windows (win32print) and Linux (CUPS) printing
- **Settings Dialog**: GUI for configuring API keys and return address
- **Error Handling**: Automatic refund on print failure, comprehensive error messages
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

The application requires a configuration file for the EasyPost API, Google Maps API, and return address information.

### Initial Setup

On first run, the application will look for `config.ini` in the current working directory. If not found, it will fall back to `config.example.ini` for loading defaults. You can create `config.ini` manually or use the Settings dialog (File → Settings) from within the application. Settings are always saved to `config.ini`.

### Manual Configuration

1.  Copy `config.example.ini` to `config.ini` in your working directory.
2.  Populate it with your API keys and return address:

    ```ini
    [ui]
    font_size = 11

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
   - Automatically refunds if printing fails

## Platform Support

- **Windows**: Uses win32print for printing (requires `--extra windows` during installation)
- **Linux**: Uses CUPS for printing via `lp` command (requires `--extra linux` during installation)

## Keyboard Shortcuts

- `Ctrl+,` - Open Settings dialog
- `Ctrl+Q` - Quit application

## Troubleshooting

### "Configuration Error" on startup
- Ensure `config.ini` or `config.example.ini` exists and is properly formatted
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
- `core/shipping.py` - EasyPost wrapper
- `core/addresses.py` - Google Maps geocoding
- `core/models.py` - Pydantic configuration models

For development setup, follow the Local Development Installation instructions above.

To enable Git hooks for linting and formatting checks:

```bash
uv run pre-commit install
```

## License

This project is developed for the Inside Books Project. For licensing information, please contact IBP directly.
