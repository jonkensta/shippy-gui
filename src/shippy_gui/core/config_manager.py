"""Centralized configuration management."""

import configparser
from dataclasses import dataclass
import logging
from typing import Optional

from pydantic import ValidationError

from shippy_gui.core.config import load_config, resolve_config_paths
from shippy_gui.core.models import Config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfigResult:
    """Outcome of a configuration load or save.

    Failures are reported rather than presented: this module is part of
    ``core`` and must not depend on Qt. Callers decide how to surface them.
    """

    ok: bool
    title: str = ""
    message: str = ""

    def __bool__(self) -> bool:
        return self.ok


class ConfigManager:
    """Manages application configuration loading, validation, and saving.

    This class centralizes all configuration handling to eliminate duplicate
    code across the application. It handles:
    - Path resolution (config.ini vs config.example.ini)
    - Loading and validating configuration
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

    def restore(self, config: Optional[Config]) -> None:
        """Put back a previously held configuration.

        Used to roll back a load whose dependent services failed to build, so
        callers never expose a config that nothing is actually running on.
        """
        self._config = config

    def load(self) -> ConfigResult:
        """Load configuration from file.

        Returns:
            A ConfigResult describing success, or the failure to present.
        """
        try:
            self._config = load_config(self._active_load_path)
            return ConfigResult(ok=True)
        except ValidationError as e:
            return self._failure(
                "Config Validation Error", f"Error loading configuration:\n\n{e}"
            )
        except (configparser.Error, OSError) as e:
            return self._failure(
                "Config Load Error", f"Error reading configuration file:\n\n{e}"
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            return self._failure(
                "Config Load Error",
                f"Unexpected error loading configuration:\n\n{e}",
            )

    def save(self, config: Config) -> ConfigResult:
        """Save configuration to file.

        Sections the caller does not manage (notably ``[parcel]``) are
        preserved by seeding the parser with the file's current contents.
        ``tests/test_settings_dialog.py`` pins that invariant.

        Args:
            config: The configuration to save.

        Returns:
            A ConfigResult describing success, or the failure to present.
        """
        try:
            config_parser = configparser.ConfigParser()
            # Seed with existing file content to preserve unmanaged sections.
            config_parser.read(self._config_path, encoding="utf-8")

            log_file = ""
            if config.ui and config.ui.log_file:
                log_file = config.ui.log_file

            config_parser["ui"] = {
                "font_size": str(config.get_font_size()),
                "default_weight": str(config.get_default_weight()),
                "log_file": log_file,
            }
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
            if config.ibp is not None:
                # Write only the populated keys. A bare "url =" round-trips
                # back through AnyHttpUrl and would fail to load.
                ibp_section = {}
                if config.ibp.url:
                    ibp_section["url"] = str(config.ibp.url)
                if config.ibp.apikey:
                    ibp_section["apikey"] = config.ibp.apikey
                config_parser["ibp"] = ibp_section
            else:
                # Both IBP fields were cleared; drop the section entirely so the
                # seeded copy above does not resurrect stale credentials.
                config_parser.remove_section("ibp")

            with open(self._config_path, "w", encoding="utf-8") as f:
                config_parser.write(f)

            self._config = config
            return ConfigResult(ok=True)
        except (configparser.Error, OSError) as e:
            return self._failure("Save Error", f"Error saving configuration:\n\n{e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            return self._failure(
                "Save Error", f"Unexpected error saving configuration:\n\n{e}"
            )

    @staticmethod
    def _failure(title: str, message: str) -> ConfigResult:
        """Log a configuration failure and describe it for the caller."""
        logger.error("%s: %s", title, message)
        return ConfigResult(ok=False, title=title, message=message)
