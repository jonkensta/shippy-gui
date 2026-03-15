"""Configuration loading utilities."""

import configparser
from dataclasses import dataclass
from importlib import resources
import os
from typing import Optional

from pydantic import ValidationError

from shippy_gui.core.constants import DEFAULT_FONT_SIZE, DEFAULT_LOG_FILENAME
from shippy_gui.core.models import Config


@dataclass(frozen=True)
class ConfigPaths:
    """Resolved config paths for the app."""

    config_path: str
    active_load_path: str


def resolve_config_paths(
    config_path: Optional[str] = None, cwd: Optional[str] = None
) -> ConfigPaths:
    """Resolve config.ini and fallback example path.

    Args:
        config_path: Optional explicit config.ini path.
        cwd: Optional working directory (defaults to os.getcwd()).

    Returns:
        ConfigPaths with the preferred config_path and active_load_path.
    """
    working_dir = cwd or os.getcwd()
    resolved_config_path = config_path or os.path.join(working_dir, "config.ini")
    example_path = os.path.join(working_dir, "config.example.ini")

    active_load_path = resolved_config_path
    if not os.path.exists(resolved_config_path) and os.path.exists(example_path):
        active_load_path = example_path

    return ConfigPaths(
        config_path=resolved_config_path, active_load_path=active_load_path
    )


def read_config_dict(path: str) -> dict:
    """Read a config file into a dictionary for validation."""
    config_parser = configparser.ConfigParser()
    config_parser.read(path)
    return {
        section: dict(config_parser[section]) for section in config_parser.sections()
    }


def load_config(path: str) -> Config:
    """Load and validate config.ini from a path."""
    config_dict = read_config_dict(path)
    return Config.model_validate(config_dict)


def get_font_size_from_path(path: str) -> int:
    """Get font size from config, with a safe default."""
    if not os.path.exists(path):
        return DEFAULT_FONT_SIZE
    try:
        return load_config(path).get_font_size()
    except (ValidationError, configparser.Error, ValueError):
        return DEFAULT_FONT_SIZE


def load_packaged_example_config() -> str:
    """Load the packaged config.example.ini contents."""
    try:
        with (
            resources.files("shippy_gui")
            .joinpath("config.example.ini")
            .open("r", encoding="utf-8") as handle
        ):
            return handle.read()
    except Exception:  # pylint: disable=broad-exception-caught
        return ""


def initialize_config_file(config_path: str) -> None:
    """Create a starter config.ini in the working directory."""
    contents = load_packaged_example_config()
    if not contents:
        raise RuntimeError(
            "Unable to load packaged config.example.ini. Please reinstall shippy-gui."
        )

    with open(config_path, "w", encoding="utf-8") as destination:
        destination.write(contents)


def resolve_log_path(config_path: str, config: Config) -> str:
    """Resolve the configured log file path with a safe default."""
    config_dir = os.path.dirname(config_path)
    default_log_path = os.path.join(config_dir, DEFAULT_LOG_FILENAME)

    try:
        log_setting = config.get_log_file(DEFAULT_LOG_FILENAME)
        if os.path.isabs(log_setting):
            return log_setting
        return os.path.join(config_dir, log_setting or DEFAULT_LOG_FILENAME)
    except Exception:  # pylint: disable=broad-exception-caught
        return default_log_path
