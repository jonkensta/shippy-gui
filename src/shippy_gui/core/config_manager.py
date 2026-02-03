"""Centralized configuration management."""

import configparser
import logging
from typing import Optional

from pydantic import ValidationError
from PySide6.QtWidgets import QMessageBox, QWidget  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.config import load_config, resolve_config_paths
from shippy_gui.core.models import Config

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""


class ConfigManager:
    """Manages application configuration loading, validation, and saving.

    This class centralizes all configuration handling to eliminate duplicate
    code across the application. It handles:
    - Path resolution (config.ini vs config.example.ini)
    - Loading and validating configuration
    - Error handling with optional UI dialogs
    - Saving configuration changes
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the ConfigManager.

        Args:
            config_path: Optional explicit path to config.ini.
                        If not provided, resolves from current working directory.
        """
        paths = resolve_config_paths(config_path)
        self._config_path = paths.config_path
        self._active_load_path = paths.active_load_path
        self._config: Optional[Config] = None

    @property
    def config_path(self) -> str:
        """Path where config will be saved (always config.ini, not example)."""
        return self._config_path

    @property
    def active_load_path(self) -> str:
        """Path from which config was loaded (may be config.example.ini)."""
        return self._active_load_path

    @property
    def config(self) -> Optional[Config]:
        """The loaded configuration, or None if not loaded."""
        return self._config

    @property
    def is_loaded(self) -> bool:
        """Whether configuration has been successfully loaded."""
        return self._config is not None

    def load(self, parent_widget: Optional[QWidget] = None) -> bool:
        """Load configuration from file.

        Args:
            parent_widget: Optional parent widget for error dialogs.
                          If None, errors are logged but no dialogs shown.

        Returns:
            True if configuration was loaded successfully, False otherwise.
        """
        try:
            self._config = load_config(self._active_load_path)
            return True
        except ValidationError as e:
            self._handle_error(
                "Config Validation Error",
                f"Error loading configuration:\n\n{e}",
                parent_widget,
            )
            return False
        except (configparser.Error, OSError) as e:
            self._handle_error(
                "Config Load Error",
                f"Error reading configuration file:\n\n{e}",
                parent_widget,
            )
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._handle_error(
                "Config Load Error",
                f"Unexpected error loading configuration:\n\n{e}",
                parent_widget,
            )
            return False

    def save(self, config: Config, parent_widget: Optional[QWidget] = None) -> bool:
        """Save configuration to file.

        Args:
            config: The configuration to save.
            parent_widget: Optional parent widget for error dialogs.

        Returns:
            True if configuration was saved successfully, False otherwise.
        """
        try:
            config_parser = configparser.ConfigParser()
            config_parser["ui"] = {"font_size": str(config.get_font_size())}
            config_parser["easypost"] = {"apikey": config.easypost.apikey}
            config_parser["googlemaps"] = {"apikey": config.googlemaps.apikey}
            config_parser["return_address"] = {
                "name": config.return_address.name,
                "street1": config.return_address.street1,
                "street2": config.return_address.street2 or "",
                "city": config.return_address.city,
                "state": config.return_address.state,
                "zipcode": config.return_address.zipcode,
            }

            with open(self._config_path, "w", encoding="utf-8") as f:
                config_parser.write(f)

            self._config = config
            return True
        except (configparser.Error, OSError) as e:
            self._handle_error(
                "Save Error",
                f"Error saving configuration:\n\n{e}",
                parent_widget,
            )
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._handle_error(
                "Save Error",
                f"Unexpected error saving configuration:\n\n{e}",
                parent_widget,
            )
            return False

    def _handle_error(
        self, title: str, message: str, parent_widget: Optional[QWidget]
    ) -> None:
        """Handle an error by logging and optionally showing a dialog.

        Args:
            title: Error dialog title.
            message: Error message.
            parent_widget: Optional parent widget for dialog.
        """
        logger.error("%s: %s", title, message)
        if parent_widget is not None:
            QMessageBox.critical(parent_widget, title, message)
