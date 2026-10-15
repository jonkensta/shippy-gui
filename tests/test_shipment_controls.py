"""Unit tests for shipment control printer refresh behavior."""

import time
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from shippy_gui.printing.models import PrinterInfo, PrinterTransport
from shippy_gui.widgets.shipment_controls import ShipmentControls


class ShipmentControlsTests(unittest.TestCase):
    """Tests for printer refresh behavior and volunteer-friendly tooltips."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_preserves_current_selection_when_still_available(
        self, mock_get_available_printers
    ):
        mock_get_available_printers.side_effect = [
            [
                PrinterInfo("Alpha 20d1:7008"),
                PrinterInfo(
                    "Beta 9999:0001",
                    is_default=True,
                    transport=PrinterTransport.USB,
                    usb_id="9999:0001",
                ),
            ],
            [
                PrinterInfo("Alpha 20d1:7008"),
                PrinterInfo("Gamma 7777:3333"),
            ],
        ]

        controls = ShipmentControls()
        controls.printer_combo.setCurrentText("Alpha 20d1:7008")

        controls.refresh_printers()

        self.assertEqual(controls.printer_name, "Alpha 20d1:7008")

    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_falls_back_to_default_then_first_available(
        self, mock_get_available_printers
    ):
        mock_get_available_printers.side_effect = [
            [PrinterInfo("Alpha 20d1:7008", is_default=True)],
            [
                PrinterInfo("Beta 9999:0001", is_default=True),
                PrinterInfo("Gamma 7777:3333"),
            ],
            [PrinterInfo("Gamma 7777:3333")],
        ]

        controls = ShipmentControls()
        controls.refresh_printers()
        self.assertEqual(controls.printer_name, "Beta 9999:0001")

        controls.refresh_printers()
        self.assertEqual(controls.printer_name, "Gamma 7777:3333")

    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_refresh_shows_no_printers_but_keeps_create_enabled_when_empty(
        self, mock_get_available_printers
    ):
        mock_get_available_printers.return_value = []

        controls = ShipmentControls()

        self.assertEqual(
            controls.printer_combo.currentText(), ShipmentControls.NO_PRINTERS_LABEL
        )
        self.assertFalse(controls.has_printers)
        self.assertEqual(controls.printer_name, "")
        self.assertIsNone(controls.validate())
        # The shipment flow asks before buying; the button itself stays usable.
        self.assertTrue(controls.create_button.isEnabled())
        self.assertEqual(
            controls.printer_status_label.text(), ShipmentControls.NO_PRINTER_TEXT
        )

    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_set_enabled_true_keeps_printer_combo_disabled_when_no_printers(
        self, mock_get_available_printers
    ):
        mock_get_available_printers.return_value = []

        controls = ShipmentControls()
        controls.set_enabled(False)
        self.assertFalse(controls.create_button.isEnabled())
        controls.set_enabled(True)

        self.assertTrue(controls.create_button.isEnabled())
        self.assertFalse(controls.printer_combo.isEnabled())
        self.assertTrue(controls.refresh_button.isEnabled())

    @patch("shippy_gui.widgets.shipment_controls.get_available_printers")
    def test_tooltips_explain_refresh_and_filtering(self, mock_get_available_printers):
        mock_get_available_printers.return_value = [PrinterInfo("Alpha 20d1:7008")]

        controls = ShipmentControls()

        self.assertIn("plugged in and turned on", controls.printer_combo.toolTip())
        self.assertIn("updates by itself", controls.printer_combo.toolTip())
        self.assertIn("scan again", controls.refresh_button.toolTip())
        self.assertIn("do not need to restart", controls.refresh_button.toolTip())
        self.assertEqual(controls.selected_printer.system_name, "Alpha 20d1:7008")
        self.assertIn("Alpha 20d1:7008", controls.printer_status_label.text())


class PrinterPollingTests(unittest.TestCase):
    """Tests for the self-updating printer list and status line."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _wait_for_poll(self, controls):
        """Let the background scan finish and its queued signal arrive."""
        deadline = time.monotonic() + 5
        while controls._poll_in_flight:  # pylint: disable=protected-access
            self.app.processEvents()
            if time.monotonic() > deadline:
                self.fail("printer poll did not finish")
            time.sleep(0.01)

    def test_poll_picks_up_a_printer_plugged_in_later(self):
        scans = [[], [PrinterInfo("Alpha 20d1:7008")]]
        controls = ShipmentControls(discover=lambda: scans.pop(0))
        updates = []
        controls.printers_updated.connect(lambda: updates.append(controls.has_printers))
        self.assertFalse(controls.has_printers)

        controls.poll_printers()
        self._wait_for_poll(controls)

        self.assertTrue(controls.has_printers)
        self.assertEqual(controls.printer_name, "Alpha 20d1:7008")
        self.assertIn(
            ShipmentControls.PRINTER_READY_TEXT, controls.printer_status_label.text()
        )
        self.assertEqual(updates, [True])

    def test_poll_notices_a_printer_unplugged(self):
        scans = [[PrinterInfo("Alpha 20d1:7008")], []]
        controls = ShipmentControls(discover=lambda: scans.pop(0))

        controls.poll_printers()
        self._wait_for_poll(controls)

        self.assertFalse(controls.has_printers)
        self.assertEqual(
            controls.printer_status_label.text(), ShipmentControls.NO_PRINTER_TEXT
        )

    def test_poll_is_paused_while_a_label_is_in_progress(self):
        calls = []

        def discover():
            calls.append(1)
            return [PrinterInfo("Alpha 20d1:7008")]

        controls = ShipmentControls(discover=discover)
        calls.clear()
        controls.set_enabled(False)

        controls.poll_printers()

        self.assertFalse(controls._poll_in_flight)  # pylint: disable=protected-access
        self.assertEqual(calls, [])

    def test_poll_failure_keeps_the_last_known_printers(self):
        def discover():
            if discover.calls:
                raise RuntimeError("WMI hiccup")
            discover.calls += 1
            return [PrinterInfo("Alpha 20d1:7008")]

        discover.calls = 0
        controls = ShipmentControls(discover=discover)

        with self.assertLogs("shippy_gui.widgets.shipment_controls", "ERROR"):
            controls.poll_printers()
            self._wait_for_poll(controls)

        self.assertTrue(controls.has_printers)

    def test_unchanged_scan_does_not_rebuild_the_list(self):
        printers = [PrinterInfo("Alpha 20d1:7008"), PrinterInfo("Beta 9999:0001")]
        controls = ShipmentControls(discover=lambda: list(printers))
        controls.printer_combo.setCurrentIndex(1)
        cleared = []
        controls.printer_combo.currentIndexChanged.connect(cleared.append)

        controls.refresh_printers()

        self.assertEqual(cleared, [])
        self.assertEqual(controls.printer_name, "Beta 9999:0001")


if __name__ == "__main__":
    unittest.main()
