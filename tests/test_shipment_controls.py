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

    def test_poll_rate_slows_once_a_printer_is_found(self):
        scans = [[], [PrinterInfo("Alpha 20d1:7008")], []]
        controls = ShipmentControls(
            discover=lambda: scans.pop(0),
            poll_interval_ms=2_000,
            found_poll_interval_ms=10_000,
        )
        timer = controls._poll_timer  # pylint: disable=protected-access
        self.assertEqual(timer.interval(), 2_000)

        controls.poll_printers()
        self._wait_for_poll(controls)
        self.assertEqual(timer.interval(), 10_000)

        controls.poll_printers()
        self._wait_for_poll(controls)
        self.assertEqual(timer.interval(), 2_000)

    def test_printer_found_and_lost_are_logged(self):
        scans = [[], [PrinterInfo("Alpha 20d1:7008")], []]
        logger_name = "shippy_gui.widgets.shipment_controls"
        with self.assertLogs(logger_name, "INFO") as logs:
            controls = ShipmentControls(discover=lambda: scans.pop(0))
            controls.poll_printers()
            self._wait_for_poll(controls)
            controls.poll_printers()
            self._wait_for_poll(controls)
        messages = [record.getMessage() for record in logs.records]
        self.assertEqual(
            messages,
            [
                "no label printer found at start-up",
                "label printer found: Alpha 20d1:7008",
                "label printer lost (was Alpha 20d1:7008)",
            ],
        )

    def test_unchanged_poll_logs_nothing(self):
        printers = [PrinterInfo("Alpha 20d1:7008")]
        controls = ShipmentControls(discover=lambda: list(printers))
        with self.assertNoLogs("shippy_gui.widgets.shipment_controls", "INFO"):
            controls.poll_printers()
            self._wait_for_poll(controls)

    def test_background_poll_runs_quietly_but_startup_scan_does_not(self):
        import ibp_printing.log  # pylint: disable=import-outside-toplevel

        quiet_flags = []

        def scan():
            # pylint: disable-next=protected-access
            quiet_flags.append(ibp_printing.log._QUIET.get())
            return [PrinterInfo("Alpha 20d1:7008")]

        controls = ShipmentControls(discover=scan)
        controls.poll_printers()
        self._wait_for_poll(controls)
        controls.refresh_printers()

        self.assertEqual(quiet_flags, [False, True, False])


@patch(
    "shippy_gui.widgets.shipment_controls.get_available_printers",
    return_value=[PrinterInfo("Alpha 20d1:7008")],
)
class SmallBoxQuestionTests(unittest.TestCase):
    """The "box is 12x12x12 or smaller" question next to the weight."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_and_disabled_under_four_pounds(self, _printers):
        controls = ShipmentControls(default_weight=3)

        self.assertTrue(controls.small_box_checkbox.isHidden())
        self.assertFalse(controls.small_box_checkbox.isEnabled())
        self.assertFalse(controls.small_box_applies)

    def test_shown_enabled_and_unticked_from_four_pounds(self, _printers):
        controls = ShipmentControls(default_weight=3)

        controls.weight_input.setValue(4)

        self.assertFalse(controls.small_box_checkbox.isHidden())
        self.assertTrue(controls.small_box_checkbox.isEnabled())
        self.assertFalse(controls.small_box_checkbox.isChecked())
        self.assertFalse(controls.small_box)

    def test_ticked_box_is_reported_as_small(self, _printers):
        controls = ShipmentControls(default_weight=8)

        controls.small_box_checkbox.setChecked(True)

        self.assertTrue(controls.small_box)

    def test_dropping_under_four_pounds_clears_the_answer(self, _printers):
        controls = ShipmentControls(default_weight=8)
        controls.small_box_checkbox.setChecked(True)

        controls.weight_input.setValue(3)
        controls.weight_input.setValue(8)

        self.assertFalse(controls.small_box_checkbox.isChecked())
        self.assertFalse(controls.small_box)

    def test_reset_after_a_label_clears_the_answer_but_keeps_weight(self, _printers):
        controls = ShipmentControls(default_weight=8)
        controls.small_box_checkbox.setChecked(True)

        controls.reset()

        self.assertFalse(controls.small_box)
        self.assertEqual(controls.weight_lbs, 8)

    def test_disabled_while_a_label_is_in_progress(self, _printers):
        controls = ShipmentControls(default_weight=8)

        controls.set_enabled(False)
        self.assertFalse(controls.small_box_checkbox.isEnabled())
        controls.set_enabled(True)
        self.assertTrue(controls.small_box_checkbox.isEnabled())

    def test_question_states_volume_and_longest_side(self, _printers):
        controls = ShipmentControls(default_weight=8)

        self.assertEqual(
            controls.small_box_checkbox.text(),
            "Box is 1,728 cu in or less (L×W×H, sides rounded up) "
            "and no side over 22 in",
        )
        tooltip = controls.small_box_checkbox.toolTip()
        self.assertIn("round it UP", tooltip)
        self.assertIn("Qualifies: 12×12×12, 18×12×8, 16×12×9, 20×10×8.", tooltip)
        self.assertIn("14×12×11 (1,848 cu in), 24×10×7", tooltip)
        self.assertIn("leave it unticked", tooltip)

    def test_clear_small_box_unticks(self, _printers):
        controls = ShipmentControls(default_weight=8)
        controls.small_box_checkbox.setChecked(True)

        controls.clear_small_box()

        self.assertFalse(controls.small_box)


if __name__ == "__main__":
    unittest.main()
