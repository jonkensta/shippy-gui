"""Unit tests for configuration helper functions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from shippy_gui.core.config import initialize_config_file, resolve_log_path
from shippy_gui.core.constants import (
    DEFAULT_PARCEL_HEIGHT_IN,
    DEFAULT_PARCEL_LENGTH_IN,
    DEFAULT_PARCEL_WIDTH_IN,
)
from shippy_gui.core.models import Config

BASE_CONFIG_DICT = {
    "easypost": {"apikey": "ep_test"},
    "googlemaps": {"apikey": "gmaps_test"},
    "return_address": {
        "name": "Inside Books Project",
        "street1": "PO Box 1",
        "city": "Austin",
        "state": "TX",
        "zipcode": "78703",
    },
}


class ConfigHelperTests(unittest.TestCase):
    """Tests for startup/config bootstrap helper functions."""

    def test_initialize_config_file_writes_packaged_example_contents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.ini"

            with patch(
                "shippy_gui.core.config.load_packaged_example_config",
                return_value="[ui]\nfont_size = 11\n",
            ):
                initialize_config_file(str(config_path))

            self.assertEqual(
                config_path.read_text(encoding="utf-8"), "[ui]\nfont_size = 11\n"
            )

    def test_resolve_log_path_uses_relative_setting_from_config(self):
        config = Config.model_validate(
            {**BASE_CONFIG_DICT, "ui": {"log_file": "custom.log"}}
        )

        log_path = resolve_log_path("/tmp/example/config.ini", config)

        self.assertEqual(log_path, "/tmp/example/custom.log")


class ParcelConfigTests(unittest.TestCase):
    """Tests for parcel dimension configuration."""

    def test_parcel_defaults_apply_when_section_missing(self):
        config = Config.model_validate(BASE_CONFIG_DICT)

        self.assertEqual(config.parcel.length, DEFAULT_PARCEL_LENGTH_IN)
        self.assertEqual(config.parcel.width, DEFAULT_PARCEL_WIDTH_IN)
        self.assertEqual(config.parcel.height, DEFAULT_PARCEL_HEIGHT_IN)

    def test_parcel_section_parses_ini_string_values(self):
        config = Config.model_validate(
            {
                **BASE_CONFIG_DICT,
                "parcel": {"length": "22", "width": "16", "height": "12"},
            }
        )

        self.assertEqual(config.parcel.length, 22.0)
        self.assertEqual(config.parcel.width, 16.0)
        self.assertEqual(config.parcel.height, 12.0)

    def test_parcel_dimensions_must_be_positive(self):
        with self.assertRaises(ValidationError):
            Config.model_validate({**BASE_CONFIG_DICT, "parcel": {"length": "0"}})


if __name__ == "__main__":
    unittest.main()
