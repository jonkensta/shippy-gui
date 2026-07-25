"""Unit tests for shipping tab coordinators and status presentation."""

import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from shippy_gui.core.constants import StatusLevel
from shippy_gui.core.models import (
    Config,
    EasypostConfig,
    GoogleMapsConfig,
    ParsedAddress,
    RecipientAddress,
    ReturnAddressConfig,
)
from shippy_gui.core.refunds import RefundOutcome
from shippy_gui.printing.models import PrintDialogResult
from shippy_gui.shipping_coordinators import (
    AddressLookupCoordinator,
    ShipmentFlowCoordinator,
    ShippingServices,
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
        self.refunded = FakeSignal()

    def start(self):
        self.started = True


def make_config() -> Config:
    """Build a minimal valid configuration for coordinator tests."""
    return Config(
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


class ShippingCoordinatorTests(unittest.TestCase):
    """Tests for extracted shipping tab presentation and workflow helpers."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Modal dialogs block forever under the offscreen platform.
        warning_patch = patch("shippy_gui.shipping_coordinators.QMessageBox.warning")
        self.mock_warning = warning_patch.start()
        self.addCleanup(warning_patch.stop)

    def test_status_presenter_updates_text_and_color(self):
        label = QLabel()
        presenter = ShippingStatusPresenter(label)

        presenter.set_status("Done", StatusLevel.SUCCESS)

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
            services=ShippingServices(address_parser=parser),
        )

        mock_single_shot.side_effect = lambda _delay, callback: callback()
        coordinator.load_address()

        self.assertEqual(address_form.street1_input.text(), "123 Main St")
        self.assertEqual(address_form.city_input.text(), "Austin")
        self.assertEqual(status_label.text(), "Address loaded successfully")
        self.assertEqual(search_input.text(), "")

    def _build_flow_coordinator(self, services, worker_factory=None):
        """Build a ShipmentFlowCoordinator with mocked widgets."""
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

        kwargs = {}
        if worker_factory is not None:
            kwargs["worker_factory"] = worker_factory

        coordinator = ShipmentFlowCoordinator(
            parent_widget=parent,
            address_search_input=search_input,
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=presenter,
            services=services,
            **kwargs,
        )
        return coordinator, address_form, shipment_controls, status_label

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_shipment_flow_starts_worker_and_handles_success(
        self, mock_keyboard_modifiers
    ):
        del mock_keyboard_modifiers
        shipment_service = Mock()
        services = ShippingServices(
            config=make_config(),
            shipment_service=shipment_service,
            logo_path="/tmp/logo.jpg",
        )
        created_workers: list[FakeWorker] = []

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            created_workers.append(worker)
            return worker

        coordinator, address_form, shipment_controls, status_label = (
            self._build_flow_coordinator(services, worker_factory)
        )

        coordinator.create_label()

        self.assertEqual(len(created_workers), 1)
        worker = created_workers[0]
        self.assertTrue(worker.started)
        self.assertEqual(worker.kwargs["shipment_service"], shipment_service)
        shipment_controls.set_enabled.assert_called_once_with(False)

        worker.success.emit("Label printed")
        address_form.clear.assert_called_once_with()
        self.assertEqual(status_label.text(), "Label printed")

        worker.finished.emit()
        self.assertIsNone(coordinator.worker)
        self.assertEqual(shipment_controls.set_enabled.call_args_list[-1].args, (True,))

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_background_refund_outcome_is_presented_not_reapplied(
        self, mock_keyboard_modifiers
    ):
        """The worker already refunded; the UI must only report it."""
        del mock_keyboard_modifiers
        shipment_service = Mock()
        services = ShippingServices(
            config=make_config(), shipment_service=shipment_service
        )
        created_workers: list[FakeWorker] = []

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            created_workers.append(worker)
            return worker

        coordinator, _, _, status_label = self._build_flow_coordinator(
            services, worker_factory
        )
        coordinator.create_label()

        created_workers[0].refunded.emit(
            RefundOutcome(reason="Printing error: offline", refunded=True)
        )

        # The refund happened in the worker thread; do not fire a second one.
        shipment_service.refund_shipment.assert_not_called()
        self.assertEqual(status_label.text(), "Printing error: offline. Refunded.")
        # A failed print must be impossible to miss, not just a status line.
        self.mock_warning.assert_called_once()

    @patch("shippy_gui.shipping_coordinators.QMessageBox.critical")
    def test_refund_without_a_bound_policy_is_escalated_not_silent(self, mock_critical):
        """An unrefundable shipment must never fail quietly."""
        coordinator, _, _, status_label = self._build_flow_coordinator(
            ShippingServices()
        )

        coordinator.refund_shipment(Mock(id="shp_123"), "Print failed")

        self.assertEqual(status_label.text(), "Refund failed")
        mock_critical.assert_called_once()
        self.assertIn("shp_123", mock_critical.call_args.args[2])

    @patch("shippy_gui.shipping_coordinators.QMessageBox.critical")
    def test_failed_refund_outcome_is_escalated(self, mock_critical):
        services = ShippingServices(shipment_service=Mock())
        coordinator, _, _, status_label = self._build_flow_coordinator(services)

        coordinator.present_refund_outcome(
            RefundOutcome(reason="Print failed", refunded=False, error="boom")
        )

        self.assertEqual(status_label.text(), "Refund failed")
        mock_critical.assert_called_once()

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.ShiftModifier,
    )
    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_refund_uses_the_buying_service_after_a_settings_reload(
        self, mock_print_dialog, mock_keyboard_modifiers
    ):
        """A reload mid-shipment must not refund against the new account."""
        del mock_keyboard_modifiers
        mock_print_dialog.return_value = PrintDialogResult.FAILED
        buying_service = Mock()
        services = ShippingServices(
            config=make_config(), shipment_service=buying_service
        )
        coordinator, _, _, _ = self._build_flow_coordinator(
            services, lambda **kwargs: FakeWorker(**kwargs)
        )
        coordinator.create_label()

        # Settings are saved while the print dialog is on screen.
        replacement_service = Mock()
        services.shipment_service = replacement_service

        shipment = Mock(id="shp_123")
        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        buying_service.refund_shipment.assert_called_once_with("shp_123")
        replacement_service.refund_shipment.assert_not_called()

    def _coordinator_ready_for_dialog(self, shipment_service):
        """Build a coordinator that has already started a shipment."""
        services = ShippingServices(
            config=make_config(), shipment_service=shipment_service
        )
        coordinator, _, _, status_label = self._build_flow_coordinator(
            services, lambda **kwargs: FakeWorker(**kwargs)
        )
        with patch(
            "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
            return_value=Qt.KeyboardModifier.ShiftModifier,
        ):
            coordinator.create_label()
        return coordinator, status_label

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_print_failure_refunds_through_the_same_policy(
        self, mock_print_dialog
    ):
        mock_print_dialog.return_value = PrintDialogResult.FAILED
        shipment_service = Mock()
        coordinator, status_label = self._coordinator_ready_for_dialog(shipment_service)

        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(status_label.text(), "Print failed. Refunded.")

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_cancel_refunds_the_shipment(self, mock_print_dialog):
        mock_print_dialog.return_value = PrintDialogResult.CANCELED
        shipment_service = Mock()
        coordinator, status_label = self._coordinator_ready_for_dialog(shipment_service)

        shipment = Mock(id="shp_456")

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_called_once_with("shp_456")
        self.assertEqual(status_label.text(), "Print canceled. Refunded.")

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_success_does_not_refund(self, mock_print_dialog):
        mock_print_dialog.return_value = PrintDialogResult.PRINTED
        shipment_service = Mock()
        coordinator, status_label = self._coordinator_ready_for_dialog(shipment_service)

        shipment = Mock(id="shp_789")
        shipment.tracking_code = "TRACK789"

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_not_called()
        self.assertIn("TRACK789", status_label.text())


if __name__ == "__main__":
    unittest.main()
