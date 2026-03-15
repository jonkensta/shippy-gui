# AGENTS.md

## Project Overview

- `shippy-gui` is a Python 3.12+ desktop application built with PySide6.
- Dependency and environment management use `uv`.
- The app entrypoint is `python -m shippy_gui` or the `shippy-gui` console script.
- Runtime configuration is loaded from `config.ini` in the current working directory.
- Source code lives under `src/shippy_gui/`.

## Repository Layout

- `src/shippy_gui/__main__.py`: application startup, config bootstrap, logging, and main window launch.
- `src/shippy_gui/main_window.py`: top-level window and menu actions.
- `src/shippy_gui/shipping_tab.py`: main shipping workflow UI.
- `src/shippy_gui/settings_dialog.py`: configuration editing and validation UI.
- `src/shippy_gui/core/`: config, models, constants, logging, fonts, and service helpers.
- `src/shippy_gui/printing/`: printer backends and printer service logic.
- `src/shippy_gui/widgets/`: reusable UI widgets.
- `src/shippy_gui/workers/`: background worker logic for network and label operations.
- `config.example.ini`: development example config.

## Environment and Setup

- Create the environment with `uv venv` and install dependencies with `uv sync`.
- Install Linux printing dependencies with `uv sync --extra linux` when working on Linux printing support.
- Install Windows printing dependencies with `uv sync --extra windows` when working on Windows printing support.
- Run the app from the repository root so `config.ini` resolves correctly.

## Working Rules

- Keep changes focused and aligned with the existing module boundaries.
- Prefer small, local edits over broad refactors unless the task requires structural changes.
- Preserve current PySide6 patterns and signal/slot flow when extending the UI.
- Do not hardcode secrets, API keys, printer names, or machine-specific paths.
- Treat `config.example.ini` as a template only; real runtime settings belong in `config.ini`.
- If you change config fields or startup behavior, update `README.md` and the example config in the same unit of work.

## Validation

- There is no dedicated test suite in the repository today.
- For code changes, run targeted validation that matches the area you touched.
- Use import or startup checks for Python modules you changed.
- Run an application launch smoke check when changing UI or startup code.
- Run platform-specific printing checks only when touching the relevant backend.
- If you cannot run a meaningful validation step, state that explicitly.

## Git Workflow

- Work on this project using branch-based development, not direct commits to `main`.
- Commit continuously in the smallest practical atomic, focused unit of work.
- Use single-line commit messages with a clear tag such as `feat:`, `bugfix:`, `docs:`, `refactor:`, `test:`, or `chore:`.
- Do not add `Co-authored-by:` trailers or similar AI-assistant attribution lines to commits.
- Do not mix unrelated changes in one commit.

## Documentation Expectations

- Update `README.md` when changing setup, configuration, platform behavior, or user-visible workflow.
- Keep instructions concrete and repository-specific; avoid generic boilerplate.
