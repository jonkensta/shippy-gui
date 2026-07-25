"""Unit tests for the settings dialog config write path."""

import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from shippy_gui.core.config import load_config
from shippy_gui.settings_dialog import SettingsDialog

BASE_INI = """[easypost]
apikey = ek_test

[googlemaps]
apikey = gm_test

[return_address]
name = Inside Books Project
street1 = 827 W 12th St
city = Austin
state = TX
zipcode = 78701

[parcel]
length = 11.0
width = 8.5
height = 3.0
"""


class SettingsDialogSaveTests(unittest.TestCase):
    """Tests for validation and persistence of settings dialog input."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.config_path = os.path.join(self._tempdir.name, "config.ini")
        with open(self.config_path, "w", encoding="utf-8") as handle:
            handle.write(BASE_INI)

    def test_save_succeeds_when_ibp_fields_are_blank(self):
        """A blank IBP URL must be omitted, not sent as "" to AnyHttpUrl."""
        dialog = SettingsDialog(self.config_path)
        dialog.ibp_url_input.setText("")
        dialog.ibp_key_input.setText("")

        with patch("shippy_gui.settings_dialog.QMessageBox.critical") as mock_critical:
            dialog._save_config()

        mock_critical.assert_not_called()
        saved = load_config(self.config_path)
        self.assertIsNone(saved.ibp)

    def test_save_persists_populated_ibp_fields(self):
        dialog = SettingsDialog(self.config_path)
        dialog.ibp_url_input.setText("https://ibp.example.com")
        dialog.ibp_key_input.setText("ibp_key")

        with patch("shippy_gui.settings_dialog.QMessageBox.critical") as mock_critical:
            dialog._save_config()

        mock_critical.assert_not_called()
        saved = load_config(self.config_path)
        assert saved.ibp is not None
        self.assertEqual(saved.ibp.apikey, "ibp_key")

    def test_save_preserves_non_default_parcel_section(self):
        """The dialog has no parcel widgets; saving must not reset dimensions."""
        dialog = SettingsDialog(self.config_path)

        with patch("shippy_gui.settings_dialog.QMessageBox.critical") as mock_critical:
            dialog._save_config()

        mock_critical.assert_not_called()
        saved = load_config(self.config_path)
        self.assertEqual(saved.parcel.length, 11.0)
        self.assertEqual(saved.parcel.width, 8.5)
        self.assertEqual(saved.parcel.height, 3.0)

    def test_return_address_round_trips_through_the_shared_form(self):
        dialog = SettingsDialog(self.config_path)
        self.assertEqual(
            dialog.return_address_form.name_input.text(), "Inside Books Project"
        )
        self.assertEqual(dialog.return_address_form.city_input.text(), "Austin")

        dialog.return_address_form.street1_input.setText("827 W 12th St")
        dialog.return_address_form.city_input.setText("Round Rock")

        with patch("shippy_gui.settings_dialog.QMessageBox.critical") as mock_critical:
            dialog._save_config()

        mock_critical.assert_not_called()
        saved = load_config(self.config_path)
        self.assertEqual(saved.return_address.city, "Round Rock")
        # The return address form hides company; a blank must not reach EasyPost.
        self.assertIsNone(saved.return_address.company)
        self.assertNotIn("company", saved.return_address.to_easypost_dict())

    def test_blank_required_return_field_is_reported(self):
        dialog = SettingsDialog(self.config_path)
        dialog.return_address_form.name_input.setText("")

        with patch("shippy_gui.settings_dialog.QMessageBox.critical") as mock_critical:
            dialog._save_config()

        mock_critical.assert_called_once()


if __name__ == "__main__":
    unittest.main()
