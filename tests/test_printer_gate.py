"""Unit tests for the "plug in the label printer" question before buying postage."""

import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from journal_fakes import install_fake_journal
from test_shipping_coordinators import FakeWorker

from shippy_gui.core.models import (
    Config,
    EasypostConfig,
    GoogleMapsConfig,
    RecipientAddress,
    ReturnAddressConfig,
)
from shippy_gui.printing.models import PrinterInfo
from shippy_gui.shipping_coordinators import (
    ShipmentFlowCoordinator,
    ShippingStatusPresenter,
)
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.printer_gate import (
    NoPrinterDialog,
    PrinterGateResult,
    wait_for_printer,
)
from shippy_gui.widgets.shipment_controls import ShipmentControls


class NoPrinterDialogTests(unittest.TestCase):
    """Tests for the self-closing no-printer dialog."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_returns_at_once_when_a_printer_is_ready(self):
        controls = ShipmentControls(discover=lambda: [PrinterInfo("Alpha 20d1:7008")])

        with patch("shippy_gui.widgets.printer_gate.NoPrinterDialog") as dialog:
            self.assertIs(
                wait_for_printer(None, controls), PrinterGateResult.PRINTER_FOUND
            )
        dialog.assert_not_called()

    def test_closes_by_itself_when_a_printer_is_plugged_in(self):
        scans = [[], [PrinterInfo("Alpha 20d1:7008")]]
        controls = ShipmentControls(discover=lambda: scans.pop(0))
        # Plug the printer in once the dialog is up; the next scan finds it.
        QTimer.singleShot(0, controls.refresh_printers)

        result = wait_for_printer(None, controls)

        self.assertIs(result, PrinterGateResult.PRINTER_FOUND)
        self.assertEqual(controls.printer_name, "Alpha 20d1:7008")

    def test_continue_anyway(self):
        controls = ShipmentControls(discover=lambda: [])
        dialog = NoPrinterDialog(controls)
        QTimer.singleShot(0, dialog.continue_button.click)

        dialog.exec()

        self.assertIs(dialog.result_choice, PrinterGateResult.CONTINUE_ANYWAY)

    def test_cancel_is_the_default(self):
        controls = ShipmentControls(discover=lambda: [])
        dialog = NoPrinterDialog(controls)
        QTimer.singleShot(0, dialog.cancel_button.click)

        dialog.exec()

        self.assertIs(dialog.result_choice, PrinterGateResult.CANCELED)
        self.assertTrue(dialog.cancel_button.isDefault())
        self.assertFalse(dialog.continue_button.isDefault())

    def test_text_explains_the_to_print_folder(self):
        dialog = NoPrinterDialog(ShipmentControls(discover=lambda: []))
        text = " ".join(label.text() for label in dialog.findChildren(QLabel))

        self.assertIn("plug in the printer", text)
        self.assertIn("Downloads\\to-print\\", text)
        self.assertIn("label watcher", text)


@patch(
    "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
    return_value=Qt.KeyboardModifier.NoModifier,
)
class ShipmentFlowPrinterGateTests(unittest.TestCase):
    """The shipment flow asks about the printer before buying postage."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        install_fake_journal(self)

    def _coordinator(self, gate_result, printer_name=""):
        address_form = Mock(spec=AddressForm)
        address_form.validate_required.return_value = None
        address_form.get_address.return_value = RecipientAddress(
            name="Reader",
            street1="123 Main St",
            city="Austin",
            state="TX",
            zipcode="78701",
        )
        self.controls = Mock(spec=ShipmentControls)
        self.controls.validate.return_value = None
        self.controls.weight_lbs = 2
        self.controls.printer_name = printer_name
        self.status_label = QLabel()
        self.workers: list[FakeWorker] = []
        self.gate = Mock(return_value=gate_result)
        config = Config(
            easypost=EasypostConfig(apikey="ep"),
            googlemaps=GoogleMapsConfig(apikey="gm"),
            return_address=ReturnAddressConfig(
                name="IBP",
                street1="456 Return Rd",
                city="Austin",
                state="TX",
                zipcode="78702",
            ),
        )

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            self.workers.append(worker)
            return worker

        return ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=QLineEdit(),
            address_form=address_form,
            shipment_controls=self.controls,
            status_presenter=ShippingStatusPresenter(self.status_label),
            get_config=lambda: config,
            get_shipment_service=Mock,
            get_logo_path=lambda: None,
            worker_factory=worker_factory,
            find_duplicates=lambda identity: [],
            confirm_printer=self.gate,
        )

    def test_cancel_buys_nothing(self, _modifiers):
        coordinator = self._coordinator(PrinterGateResult.CANCELED)

        coordinator.create_label()

        self.gate.assert_called_once()
        self.assertEqual(self.workers, [])
        self.controls.set_enabled.assert_not_called()
        self.assertIn("NOT created", self.status_label.text())

    def test_continue_anyway_buys_without_a_printer(self, _modifiers):
        coordinator = self._coordinator(PrinterGateResult.CONTINUE_ANYWAY)

        with self.assertLogs("shippy_gui.shipping_coordinators", "WARNING"):
            coordinator.create_label()

        self.assertEqual(len(self.workers), 1)
        self.assertTrue(self.workers[0].started)
        self.assertEqual(self.workers[0].kwargs["printer_name"], "")

    def test_printer_found_prints_to_it(self, _modifiers):
        coordinator = self._coordinator(
            PrinterGateResult.PRINTER_FOUND, printer_name="Alpha 20d1:7008"
        )

        coordinator.create_label()

        self.assertEqual(self.workers[0].kwargs["printer_name"], "Alpha 20d1:7008")

    def test_shift_click_skips_the_printer_check(self, modifiers):
        modifiers.return_value = Qt.KeyboardModifier.ShiftModifier
        coordinator = self._coordinator(PrinterGateResult.CANCELED)

        coordinator.create_label()

        self.gate.assert_not_called()
        self.assertTrue(self.workers[0].kwargs["use_dialog"])


if __name__ == "__main__":
    unittest.main()
