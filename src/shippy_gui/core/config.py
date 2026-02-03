"""Configuration loading utilities."""

from dataclasses import dataclass
import configparser
import os
from typing import Optional

from pydantic import ValidationError

from shippy_gui.core.models import Config

DEFAULT_FONT_SIZE = 11


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
