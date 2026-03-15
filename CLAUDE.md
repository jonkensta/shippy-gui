# shippy-gui — Claude Code Instructions

## Project Overview

`shippy-gui` is a PySide6 desktop application for the Inside Books Project (IBP) that streamlines printing shipping labels for books sent to incarcerated individuals in Texas. It integrates with EasyPost for postage/label generation and Google Maps for address autocomplete.

**Package name:** `shippy_gui`
**Entry point:** `src/shippy_gui/__main__.py` → `main()`
**Python version:** 3.12 (see `.python-version`)
**Dependency/environment manager:** `uv` (lockfile: `uv.lock`)

## Project Structure

```
src/shippy_gui/
  __main__.py          # App entry point; config bootstrap and startup
  main_window.py       # Top-level QMainWindow
  shipping_tab.py      # Main shipping form tab
  settings_dialog.py   # Settings/config dialog
  core/
    config.py          # INI loading via configparser
    config_manager.py  # ConfigManager class (load/save/validate)
    models.py          # Pydantic models for config validation
    constants.py       # App-wide constants
    services.py        # EasyPost API wrapper
    addresses.py       # Google Maps geocoding/autocomplete
    logging.py         # Logging setup
    font.py            # Font size application
    misc.py
  widgets/
    address_form.py    # Address entry widget
    shipment_controls.py
    autocomplete.py    # Google Maps autocomplete widget
  workers/
    shipment_worker.py # QThread worker for async shipment creation
  printing/
    printer_manager.py
    printer_service.py
    backends/
      base.py
      linux.py         # CUPS printing
      windows.py       # win32print printing
  assets/
    logo.jpg           # IBP logo overlaid on labels
  config.example.ini   # Bundled template; also in repo root for dev
```

## Environment Setup

```bash
uv venv
source .venv/bin/activate
uv sync --extra linux   # or --extra windows on Windows
uv run pre-commit install
```

## Running the App

```bash
python -m shippy_gui
# or
shippy-gui
```

## Configuration

- `config.ini` in the working directory (gitignored, never commit)
- `config.example.ini` is the template (committed to repo)
- On first launch, the app auto-creates `config.ini` from the bundled example and opens the Settings dialog

## Code Quality

Pre-commit hooks run on every commit:
- `pylint` — `uv run pylint src`
- `mypy` — `uv run mypy src`
- `black --check` — `uv run black --check src`

Format code before committing: `uv run black src`

Run tests (requires offscreen Qt platform for headless/hook contexts):
```bash
QT_QPA_PLATFORM=offscreen uv run python -m unittest discover -s tests
```

## Git Workflow

- All work is done on **feature branches** branched from `main`.
- Commits must be **atomic and focused** — each commit should represent the smallest coherent unit of change.
- Use **single-line commit messages** with an appropriate conventional tag:
  - `feat:` — new feature
  - `bugfix:` — bug fix
  - `refactor:` — code restructuring without behavior change
  - `chore:` — build, deps, tooling, config
  - `docs:` — documentation only
  - `test:` — tests only
- Do **not** include "Co-Authored-By" or any AI attribution in commit messages.
- Merge to `main` via pull request.

## Key Patterns

- Configuration is validated with Pydantic models (`core/models.py`); always use `ConfigManager` or `load_config()` — never read `config.ini` directly.
- Network operations (EasyPost, Google Maps) run in `QThread` workers to keep the UI non-blocking.
- Printing is platform-dispatched through `printing/backends/`; do not add platform checks outside those modules.
- The app automatically refunds the EasyPost shipment if printing fails — preserve this invariant when touching `shipment_worker.py`.
