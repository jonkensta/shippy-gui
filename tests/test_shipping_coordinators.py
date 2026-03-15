"""Unit tests for shipping tab coordinators and status presentation."""

import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from shippy_gui.core.models import (
    Config,
    EasypostConfig,
    GoogleMapsConfig,
    ParsedAddress,
    RecipientAddress,
    ReturnAddressConfig,
)
from shippy_gui.shipping_coordinators import (
    AddressLookupCoordinator,
    ShipmentFlowCoordinator,
    ShippingStatusPresenter,
)
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.shipment_controls import ShipmentControls


class FakeSignal:
    """Simple Qt-like signal stand-in for coordinator tests."""

    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self._callbacks):
            callback(*args)


class FakeWorker:
    """Shipment worker stub that records start state and exposes signals."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.progress = FakeSignal()
        self.warning = FakeSignal()
        self.success = FakeSignal()
        self.error = FakeSignal()
        self.finished = FakeSignal()
        self.label_ready = FakeSignal()

    def start(self):
        self.started = True


class ShippingCoordinatorTests(unittest.TestCase):
    """Tests for extracted shipping tab presentation and workflow helpers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_status_presenter_updates_text_and_color(self):
        label = QLabel()
        presenter = ShippingStatusPresenter(label)

        presenter.set_status("Done", "success")

        self.assertEqual(label.text(), "Done")
        self.assertIn("font-weight: bold", label.styleSheet())

    @patch("shippy_gui.shipping_coordinators.QTimer.singleShot")
    def test_address_lookup_merges_fields_and_reports_success(self, mock_single_shot):
        parent = QWidget()
        search_input = QLineEdit()
        search_input.setText("123 Main")
        address_form = AddressForm()
        status_label = QLabel()
        presenter = ShippingStatusPresenter(status_label)
        parser = Mock(
            return_value=ParsedAddress(
                street1="123 Main St",
                city="Austin",
                state="TX",
                zipcode="78701",
            )
        )

        coordinator = AddressLookupCoordinator(
            parent_widget=parent,
            search_input=search_input,
            address_form=address_form,
            status_presenter=presenter,
            get_address_parser=lambda: parser,
            get_address_completer=lambda: None,
        )

        mock_single_shot.side_effect = lambda _delay, callback: callback()
        coordinator.load_address()

        self.assertEqual(address_form.street1_input.text(), "123 Main St")
        self.assertEqual(address_form.city_input.text(), "Austin")
        self.assertEqual(status_label.text(), "Address loaded successfully")
        self.assertEqual(search_input.text(), "")

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_shipment_flow_starts_worker_and_handles_success(
        self, mock_keyboard_modifiers
    ):
        del mock_keyboard_modifiers
        parent = QWidget()
        search_input = QLineEdit()
        address_form = Mock(spec=AddressForm)
        address_form.validate_required.return_value = None
        address_form.get_address.return_value = RecipientAddress(
            name="Reader",
            street1="123 Main St",
            city="Austin",
            state="TX",
            zipcode="78701",
        )
        shipment_controls = Mock(spec=ShipmentControls)
        shipment_controls.validate.return_value = None
        shipment_controls.weight_lbs = 2
        shipment_controls.printer_name = "Alpha 20d1:7008"
        status_label = QLabel()
        presenter = ShippingStatusPresenter(status_label)
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
        shipment_service = Mock()
        created_workers: list[FakeWorker] = []

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            created_workers.append(worker)
            return worker

        coordinator = ShipmentFlowCoordinator(
            parent_widget=parent,
            address_search_input=search_input,
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=presenter,
            get_config=lambda: config,
            get_shipment_service=lambda: shipment_service,
            get_logo_path=lambda: "/tmp/logo.jpg",
            worker_factory=worker_factory,
        )

        coordinator.create_label()

        self.assertEqual(len(created_workers), 1)
        worker = created_workers[0]
        self.assertTrue(worker.started)
        self.assertEqual(worker.kwargs["shipment_service"], shipment_service)
        shipment_controls.set_enabled.assert_called_once_with(False)

        worker.success.emit("Label printed")
        address_form.clear.assert_called_once_with()
        shipment_controls.reset.assert_called_once_with()
        self.assertEqual(status_label.text(), "Label printed")

        worker.finished.emit()
        self.assertIsNone(coordinator.worker)
        self.assertEqual(shipment_controls.set_enabled.call_args_list[-1].args, (True,))

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_shipment_flow_refunds_after_dialog_failure(self, mock_print_dialog):
        mock_print_dialog.return_value = "failed"
        parent = QWidget()
        search_input = QLineEdit()
        address_form = Mock(spec=AddressForm)
        shipment_controls = Mock(spec=ShipmentControls)
        status_label = QLabel()
        presenter = ShippingStatusPresenter(status_label)
        shipment_service = Mock()
        coordinator = ShipmentFlowCoordinator(
            parent_widget=parent,
            address_search_input=search_input,
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=presenter,
            get_config=lambda: None,
            get_shipment_service=lambda: shipment_service,
            get_logo_path=lambda: None,
        )
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(status_label.text(), "Print failed. Refunded.")


if __name__ == "__main__":
    unittest.main()
