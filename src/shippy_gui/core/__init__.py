"""Core module for shippy-gui.

This module provides configuration, models, and utility functions.
"""

from shippy_gui.core.config import (
    ConfigPaths,
    load_config,
    resolve_config_paths,
    get_font_size_from_path,
)
from shippy_gui.core.config_manager import ConfigManager
from shippy_gui.core.models import Config

__all__ = [
    "ConfigPaths",
    "ConfigManager",
    "Config",
    "load_config",
    "resolve_config_paths",
    "get_font_size_from_path",
]
