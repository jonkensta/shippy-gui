"""Unit tests for configuration helper functions."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shippy_gui.core.config import initialize_config_file, resolve_log_path
from shippy_gui.core.models import Config


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
            {
                "ui": {"log_file": "custom.log"},
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
        )

        log_path = resolve_log_path("/tmp/example/config.ini", config)

        self.assertEqual(log_path, "/tmp/example/custom.log")


if __name__ == "__main__":
    unittest.main()
