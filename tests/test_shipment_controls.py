"""Unit tests for shipment control printer refresh behavior."""

import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from shippy_gui.widgets.shipment_controls import ShipmentControls


class ShipmentControlsTests(unittest.TestCase):
    """Tests for printer refresh behavior and volunteer-friendly tooltips."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("shippy_gui.widgets.shipment_controls.get_default_printer")
    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_preserves_current_selection_when_still_available(
        self, mock_get_available_printers, mock_get_default_printer
    ):
        mock_get_available_printers.side_effect = [
            ["Alpha 20d1:7008", "Beta 9999:0001"],
            ["Alpha 20d1:7008", "Gamma 7777:3333"],
        ]
        mock_get_default_printer.return_value = "Beta 9999:0001"

        controls = ShipmentControls()
        controls.printer_combo.setCurrentText("Alpha 20d1:7008")

        controls.refresh_printers()

        self.assertEqual(controls.printer_name, "Alpha 20d1:7008")

    @patch("shippy_gui.widgets.shipment_controls.get_default_printer")
    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_falls_back_to_default_then_first_available(
        self, mock_get_available_printers, mock_get_default_printer
    ):
        mock_get_available_printers.side_effect = [
            ["Alpha 20d1:7008"],
            ["Beta 9999:0001", "Gamma 7777:3333"],
            ["Gamma 7777:3333"],
        ]
        mock_get_default_printer.side_effect = [
            "Alpha 20d1:7008",
            "Beta 9999:0001",
            None,
        ]

        controls = ShipmentControls()
        controls.refresh_printers()
        self.assertEqual(controls.printer_name, "Beta 9999:0001")

        controls.refresh_printers()
        self.assertEqual(controls.printer_name, "Gamma 7777:3333")

    @patch("shippy_gui.widgets.shipment_controls.get_default_printer")
    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_shows_no_printers_and_disables_create_when_empty(
        self, mock_get_available_printers, mock_get_default_printer
    ):
        mock_get_available_printers.return_value = []
        mock_get_default_printer.return_value = None

        controls = ShipmentControls()

        self.assertEqual(
            controls.printer_combo.currentText(), ShipmentControls.NO_PRINTERS_LABEL
        )
        self.assertFalse(controls.create_button.isEnabled())

    @patch("shippy_gui.widgets.shipment_controls.get_default_printer")
    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_tooltips_explain_refresh_and_filtering(
        self, mock_get_available_printers, mock_get_default_printer
    ):
        mock_get_available_printers.return_value = ["Alpha 20d1:7008"]
        mock_get_default_printer.return_value = None

        controls = ShipmentControls()

        self.assertIn("plugged in and turned on", controls.printer_combo.toolTip())
        self.assertIn("click Refresh", controls.printer_combo.toolTip())
        self.assertIn("scan again", controls.refresh_button.toolTip())
        self.assertIn("do not need to restart", controls.refresh_button.toolTip())


if __name__ == "__main__":
    unittest.main()
