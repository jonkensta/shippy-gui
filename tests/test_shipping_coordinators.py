"""Unit tests for shipping tab coordinators and status presentation."""

import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QWidget

from journal_fakes import install_fake_journal, make_record

from shippy_gui.core.constants import STATUS_COLORS
from shippy_gui.core.models import (
    Config,
    EasypostConfig,
    GoogleMapsConfig,
    ParsedAddress,
    RecipientAddress,
    ReturnAddressConfig,
)
from shippy_gui.core.shipment_workflow import (
    ShipmentWorkflowResult,
    ShipmentWorkflowStatus,
)
from shippy_gui.core.label_journal import LabelIdentity
from shippy_gui.core.rates import RateSummary
from shippy_gui.printing.printer_manager import DialogPrintStatus
from shippy_gui.shipping_coordinators import (
    AddressLookupCoordinator,
    ShipmentFlowCoordinator,
    ShippingStatusPresenter,
)
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.printer_gate import PrinterGateResult
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
        self.success_with_warning = FakeSignal()
        self.label_saved = FakeSignal()
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

    def setUp(self):
        self.journal = install_fake_journal(self)

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

    def _flow_with_small_box_answer(
        self,
    ):
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
        shipment_controls.weight_lbs = 8
        shipment_controls.small_box = True
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
        return coordinator, created_workers[0], status_label

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_small_box_answer_reaches_worker_and_rates_shown(self, _modifiers):
        _coordinator, worker, status_label = self._flow_with_small_box_answer()
        self.assertIs(worker.kwargs["small_box"], True)

        worker.rate_summary = RateSummary(
            text="Library Mail $9.12 · Ground Advantage $8.40 → "
            "bought Ground Advantage (cheapest)",
            library_mail_missing=False,
        )
        worker.success.emit("Label printed")

        self.assertEqual(
            status_label.text(),
            "Label printed\nLibrary Mail $9.12 · Ground Advantage $8.40 → "
            "bought Ground Advantage (cheapest)",
        )
        self.assertIn(STATUS_COLORS["success"], status_label.styleSheet())

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_missing_library_mail_shows_warning_status(self, _modifiers):
        _coordinator, worker, status_label = self._flow_with_small_box_answer()

        worker.rate_summary = RateSummary(
            text="WARNING: no Library Mail rate was quoted. Ground Advantage $8.40",
            library_mail_missing=True,
        )
        worker.success.emit("Label printed")

        self.assertIn("no Library Mail rate was quoted", status_label.text())
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())

    @patch("shippy_gui.shipping_coordinators.QMessageBox.warning")
    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_shipment_flow_warns_when_spooled_label_may_not_have_printed(
        self, mock_keyboard_modifiers, mock_warning
    ):
        del mock_keyboard_modifiers
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
        created_workers: list[FakeWorker] = []

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            created_workers.append(worker)
            return worker

        coordinator = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=QLineEdit(),
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=ShippingStatusPresenter(status_label),
            get_config=Mock,
            get_shipment_service=Mock,
            get_logo_path=lambda: None,
            worker_factory=worker_factory,
        )
        coordinator.create_label()

        created_workers[0].success_with_warning.emit("It may NOT have printed")

        address_form.clear.assert_called_once_with()
        self.assertEqual(status_label.text(), "It may NOT have printed")
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())
        mock_warning.assert_called_once()
        self.assertIn("It may NOT have printed", mock_warning.call_args.args[2])

    @patch("shippy_gui.shipping_coordinators.show_label_queued")
    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_shipment_flow_clears_form_and_warns_when_label_saved(
        self, mock_keyboard_modifiers, mock_show_queued
    ):
        del mock_keyboard_modifiers
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
        created_workers: list[FakeWorker] = []

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            created_workers.append(worker)
            return worker

        coordinator = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=QLineEdit(),
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=ShippingStatusPresenter(status_label),
            get_config=Mock,
            get_shipment_service=Mock,
            get_logo_path=lambda: None,
            worker_factory=worker_factory,
        )
        coordinator.create_label()

        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        created_workers[0].label_saved.emit(
            ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.SUCCESS,
                message="The label did NOT print: saved",
                shipment=shipment,
                saved_label_path=Path("/tmp/to-print/TRACK123.png"),
                identity=LabelIdentity("key", "Jane Doe, Huntsville"),
            )
        )

        # Postage was kept: the form is cleared so it is not bought twice.
        address_form.clear.assert_called_once_with()
        self.assertIn("Label QUEUED for Jane Doe, Huntsville", status_label.text())
        self.assertIn("TRACK123", status_label.text())
        self.assertIn("Do NOT create it again", status_label.text())
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())
        mock_show_queued.assert_called_once()
        self.assertEqual(
            mock_show_queued.call_args.args[1:],
            ("Jane Doe, Huntsville", "TRACK123", "The label did NOT print: saved"),
        )

    def _guarded_coordinator(self, answer):
        """A coordinator whose duplicate question is answered with ``answer``."""
        address_form = Mock(spec=AddressForm)
        address_form.validate_required.return_value = None
        address_form.get_address.return_value = RecipientAddress(
            name="Jane Doe",
            street1="123 Prison Rd",
            city="Huntsville",
            state="TX",
            zipcode="77340",
        )
        shipment_controls = Mock(spec=ShipmentControls)
        shipment_controls.validate.return_value = None
        shipment_controls.weight_lbs = 2
        shipment_controls.printer_name = "Alpha 20d1:7008"
        status_label = QLabel()
        workers: list[FakeWorker] = []
        confirm = Mock(return_value=answer)
        done = Mock()

        def worker_factory(**kwargs):
            worker = FakeWorker(**kwargs)
            workers.append(worker)
            return worker

        coordinator = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=QLineEdit(),
            address_form=address_form,
            shipment_controls=shipment_controls,
            status_presenter=ShippingStatusPresenter(status_label),
            get_config=Mock,
            get_shipment_service=Mock,
            get_logo_path=lambda: None,
            worker_factory=worker_factory,
            confirm_duplicate=confirm,
            on_shipment_done=done,
        )
        return coordinator, workers, confirm, status_label, shipment_controls, done

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_duplicate_declined_buys_nothing(self, _mock_modifiers):
        self.journal.duplicates = [make_record()]
        coordinator, workers, confirm, status_label, controls, _done = (
            self._guarded_coordinator(answer=False)
        )

        with self.assertLogs("shippy_gui.shipping_coordinators", "WARNING") as logs:
            coordinator.create_label()

        self.assertEqual(workers, [])  # no worker: no postage bought
        controls.set_enabled.assert_not_called()
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.args[1], self.journal.duplicates)
        self.assertEqual(
            self.journal.duplicate_queries,
            [("jane doe|123 prison rd|huntsville|tx|77340", 12)],
        )
        self.assertIn("NOT to create another label", logs.output[0])
        self.assertIn("9400OLD", logs.output[0])
        self.assertIn("Label NOT created", status_label.text())
        self.assertIn("9400OLD", status_label.text())

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_duplicate_confirmed_creates_label(self, _mock_modifiers):
        self.journal.duplicates = [make_record()]
        coordinator, workers, confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )

        with self.assertLogs("shippy_gui.shipping_coordinators", "WARNING") as logs:
            coordinator.create_label()

        confirm.assert_called_once()
        self.assertIn("to create another label", logs.output[0])
        self.assertEqual(len(workers), 1)
        self.assertTrue(workers[0].started)
        self.assertEqual(workers[0].kwargs["to_address"].name, "Jane Doe")
        controls.set_enabled.assert_called_once_with(False)

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_no_duplicate_skips_question_and_refreshes_when_done(self, _mock_modifiers):
        coordinator, workers, confirm, _label, _controls, done = (
            self._guarded_coordinator(answer=False)
        )

        coordinator.create_label()

        confirm.assert_not_called()
        self.assertEqual(len(workers), 1)
        done.assert_not_called()
        workers[0].finished.emit()
        done.assert_called_once_with()

    def _dialog_coordinator(self, shipment_service):
        """A coordinator wired for the Shift+Click dialog path."""
        status_label = QLabel()
        coordinator = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=QLineEdit(),
            address_form=Mock(spec=AddressForm),
            shipment_controls=Mock(spec=ShipmentControls),
            status_presenter=ShippingStatusPresenter(status_label),
            get_config=lambda: None,
            get_shipment_service=lambda: shipment_service,
            get_logo_path=lambda: None,
        )
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        return coordinator, status_label, shipment

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_cancel_refunds(self, mock_print_dialog):
        mock_print_dialog.return_value = DialogPrintStatus.CANCELED
        shipment_service = Mock()
        coordinator, status_label, shipment = self._dialog_coordinator(shipment_service)

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(status_label.text(), "Print canceled. Refunded.")
        self.assertEqual(self.journal.status_updates, [("TRACK123", "refunded", None)])

    @patch("shippy_gui.shipping_coordinators.show_label_queued")
    @patch("shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry")
    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_not_sent_saves_label_without_refund(
        self, mock_print_dialog, mock_save, mock_show_queued
    ):
        mock_print_dialog.return_value = DialogPrintStatus.NOT_SENT
        saved = Path("/home/v/Downloads/to-print/TRACK123.png")
        mock_save.return_value = saved
        shipment_service = Mock()
        coordinator, status_label, shipment = self._dialog_coordinator(shipment_service)
        image = object()
        prepared = ShipmentWorkflowResult(
            status=ShipmentWorkflowStatus.READY,
            message="",
            shipment=shipment,
            identity=LabelIdentity("key", "Jane Doe, Huntsville"),
        )

        coordinator._on_label_ready(image, "Alpha 20d1:7008", shipment, prepared)

        mock_save.assert_called_once_with(image, name="TRACK123", meta=ANY)
        meta = mock_save.call_args.kwargs["meta"]
        self.assertEqual(meta["recipient_label"], "Jane Doe, Huntsville")
        self.assertEqual(meta["tracking_code"], "TRACK123")
        shipment_service.refund_shipment.assert_not_called()
        self.assertIn("Label QUEUED", status_label.text())
        mock_show_queued.assert_called_once()
        self.assertEqual(mock_show_queued.call_args.args[1], "Jane Doe, Huntsville")
        self.assertIn("DELETE it from", mock_show_queued.call_args.args[3])
        self.assertEqual(
            self.journal.status_updates, [("TRACK123", "queued", str(saved))]
        )

    @patch("shippy_gui.shipping_coordinators.QMessageBox")
    @patch(
        "shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry",
        side_effect=OSError("disk full"),
    )
    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_not_sent_refunds_when_save_fails(
        self, mock_print_dialog, _mock_save, mock_box
    ):
        mock_print_dialog.return_value = DialogPrintStatus.NOT_SENT
        shipment_service = Mock()
        coordinator, _status_label, shipment = self._dialog_coordinator(
            shipment_service
        )

        with self.assertLogs("shippy_gui.core.shipment_workflow", "ERROR"):
            coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_called_once_with("shp_123")
        mock_box.critical.assert_called_once()
        self.assertIn("Refund requested", mock_box.critical.call_args.args[2])

    @patch("shippy_gui.shipping_coordinators.QMessageBox")
    @patch("shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry")
    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_failure_after_start_warns_without_refund(
        self, mock_print_dialog, mock_save, mock_box
    ):
        mock_print_dialog.return_value = DialogPrintStatus.UNCERTAIN
        shipment_service = Mock()
        coordinator, status_label, shipment = self._dialog_coordinator(shipment_service)

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        shipment_service.refund_shipment.assert_not_called()
        mock_save.assert_not_called()
        mock_box.warning.assert_called_once()
        self.assertEqual(mock_box.warning.call_args.args[1], "Check The Printer")
        self.assertIn("may or may NOT have printed", status_label.text())
        self.assertIn("TRACK123", status_label.text())
        self.assertEqual(self.journal.statuses(), ["check_printer"])

    @patch("shippy_gui.shipping_coordinators.print_image_with_dialog")
    def test_dialog_printed_marks_label_printed(self, mock_print_dialog):
        mock_print_dialog.return_value = DialogPrintStatus.PRINTED
        coordinator, _status_label, shipment = self._dialog_coordinator(Mock())

        coordinator._on_label_ready(object(), "Alpha 20d1:7008", shipment)

        self.assertEqual(self.journal.status_updates, [("TRACK123", "printed", None)])

    # --- box answer and quoted rates are never carried to another package ---

    _RATES = RateSummary(
        text="Library Mail $9.12 · Ground Advantage $8.40 → "
        "bought Ground Advantage (cheapest)",
        library_mail_missing=False,
    )

    def test_recipient_change_clears_box_answer(self):
        coordinator, _workers, _confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        # pylint: disable=protected-access
        coordinator._address_form.recipient_changed.connect.assert_called_once_with(
            coordinator._on_recipient_changed
        )

        controls.clear_small_box.return_value = False
        coordinator._on_recipient_changed()

        controls.clear_small_box.assert_called_once_with()

    def test_clearing_a_ticked_box_on_recipient_change_warns(self):
        coordinator, _workers, _confirm, status_label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        controls.clear_small_box.return_value = True

        coordinator._on_recipient_changed()  # pylint: disable=protected-access

        self.assertEqual(
            status_label.text(), ShipmentFlowCoordinator.BOX_ANSWER_CLEARED_TEXT
        )
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())

    def test_recipient_change_with_unticked_box_says_nothing(self):
        coordinator, _workers, _confirm, status_label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        status_label.setText("Address loaded successfully")
        controls.clear_small_box.return_value = False

        coordinator._on_recipient_changed()  # pylint: disable=protected-access

        self.assertEqual(status_label.text(), "Address loaded successfully")

    def test_success_with_real_widgets_shows_no_cleared_notice(self):
        """A label's own form clearing must not report a cleared box answer."""
        coordinator, _workers, _confirm, status_label, _controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        form = AddressForm()
        with patch(
            "shippy_gui.widgets.shipment_controls.get_available_printers",
            return_value=[],
        ):
            controls = ShipmentControls(default_weight=8)
        controls.small_box_checkbox.setChecked(True)
        # pylint: disable=protected-access
        coordinator._address_form = form
        coordinator._shipment_controls = controls
        form.recipient_changed.connect(coordinator._on_recipient_changed)
        coordinator.worker = Mock(rate_summary=None)

        coordinator._on_shipment_success("Label printed")

        self.assertEqual(status_label.text(), "Label printed")
        self.assertFalse(controls.small_box)

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_duplicate_declined_clears_box_answer(self, _mock_modifiers):
        self.journal.duplicates = [make_record()]
        coordinator, _workers, _confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=False)
        )

        with self.assertLogs("shippy_gui.shipping_coordinators", "WARNING"):
            coordinator.create_label()

        controls.clear_small_box.assert_called_once_with()

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_printer_gate_cancel_clears_box_answer(self, _mock_modifiers):
        coordinator, workers, _confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        # pylint: disable=protected-access
        coordinator._confirm_printer = Mock(return_value=PrinterGateResult.CANCELED)

        coordinator.create_label()

        self.assertEqual(workers, [])
        controls.clear_small_box.assert_called_once_with()

    @patch("shippy_gui.shipping_coordinators.QMessageBox.critical")
    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_shipment_error_clears_box_answer(self, _mock_modifiers, _critical):
        coordinator, workers, _confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        coordinator.create_label()

        workers[0].error.emit("Shipment creation failed: boom")

        controls.clear_small_box.assert_called_once_with()

    @patch(
        "shippy_gui.shipping_coordinators.QApplication.keyboardModifiers",
        return_value=Qt.KeyboardModifier.NoModifier,
    )
    def test_create_label_drops_stale_rate_summary(self, _mock_modifiers):
        coordinator, workers, _confirm, status_label, _controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        coordinator._rate_summary = self._RATES  # pylint: disable=protected-access

        coordinator.create_label()
        workers[0].success.emit("Label printed")

        self.assertEqual(status_label.text(), "Label printed")

    @patch("shippy_gui.shipping_coordinators.QMessageBox.warning")
    def test_check_printer_warning_keeps_rates_visible(self, _warning):
        coordinator, _workers, _confirm, status_label, _controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        coordinator.worker = Mock(rate_summary=self._RATES)

        # pylint: disable=protected-access
        coordinator._on_shipment_success_with_warning("Check the printer")

        self.assertEqual(status_label.text(), f"Check the printer\n{self._RATES.text}")
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())

    @patch("shippy_gui.shipping_coordinators.show_label_queued")
    def test_queued_label_keeps_rates_visible(self, _show_queued):
        coordinator, _workers, _confirm, status_label, _controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        coordinator.worker = Mock(rate_summary=self._RATES)
        shipment = Mock(id="shp_1", tracking_code="TRACK1")
        result = ShipmentWorkflowResult(
            status=ShipmentWorkflowStatus.SUCCESS,
            message="The label did NOT print: saved",
            shipment=shipment,
        )

        coordinator._on_label_saved(result)  # pylint: disable=protected-access

        self.assertIn("Label QUEUED", status_label.text())
        self.assertTrue(status_label.text().endswith(self._RATES.text))

    def test_validation_error_clears_box_answer(self):
        coordinator, workers, _confirm, status_label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        # pylint: disable=protected-access
        coordinator._address_form.validate_required.return_value = (
            "Please enter ZIP code"
        )

        coordinator.create_label()

        self.assertEqual(workers, [])
        controls.clear_small_box.assert_called_once_with()
        self.assertEqual(status_label.text(), "Please enter ZIP code")

    @patch("shippy_gui.shipping_coordinators.QMessageBox.critical")
    def test_missing_services_clears_box_answer(self, mock_critical):
        coordinator, workers, _confirm, _label, controls, _done = (
            self._guarded_coordinator(answer=True)
        )
        coordinator._get_shipment_service = (
            lambda: None
        )  # pylint: disable=protected-access

        coordinator.create_label()

        self.assertEqual(workers, [])
        controls.clear_small_box.assert_called_once_with()
        mock_critical.assert_called_once()

    def test_quick_lookup_after_ticking_keeps_cleared_notice(self):
        """The real lookup path: merge clears the box, then "loaded" is shown."""
        search_input = QLineEdit()
        search_input.setText("123 Main")
        address_form = AddressForm()
        status_label = QLabel()
        presenter = ShippingStatusPresenter(status_label)
        with patch(
            "shippy_gui.widgets.shipment_controls.get_available_printers",
            return_value=[],
        ):
            controls = ShipmentControls(default_weight=8)
        # Keep a reference: Qt drops connections to collected slots.
        flow = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=search_input,
            address_form=address_form,
            shipment_controls=controls,
            status_presenter=presenter,
            get_config=lambda: None,
            get_shipment_service=lambda: None,
            get_logo_path=lambda: None,
        )
        lookup = AddressLookupCoordinator(
            parent_widget=QWidget(),
            search_input=search_input,
            address_form=address_form,
            status_presenter=presenter,
            get_address_parser=lambda: Mock(
                return_value=ParsedAddress(
                    street1="123 Main St", city="Austin", state="TX", zipcode="78701"
                )
            ),
            get_address_completer=lambda: None,
        )
        controls.small_box_checkbox.setChecked(True)

        lookup.load_address()
        del flow

        self.assertFalse(controls.small_box)
        self.assertEqual(
            status_label.text(),
            "Address loaded successfully. Box size answer cleared - tick it "
            "again if the box still qualifies",
        )
        self.assertIn(STATUS_COLORS["warning"], status_label.styleSheet())

        # The notice lapses once control returns to Qt.
        QApplication.processEvents()
        presenter.set_status("Parsing address: next...", "info")
        self.assertEqual(status_label.text(), "Parsing address: next...")

    def test_quick_lookup_without_tick_reports_plain_success(self):
        search_input = QLineEdit()
        search_input.setText("123 Main")
        address_form = AddressForm()
        status_label = QLabel()
        presenter = ShippingStatusPresenter(status_label)
        with patch(
            "shippy_gui.widgets.shipment_controls.get_available_printers",
            return_value=[],
        ):
            controls = ShipmentControls(default_weight=8)
        # Keep a reference: Qt drops connections to collected slots.
        flow = ShipmentFlowCoordinator(
            parent_widget=QWidget(),
            address_search_input=search_input,
            address_form=address_form,
            shipment_controls=controls,
            status_presenter=presenter,
            get_config=lambda: None,
            get_shipment_service=lambda: None,
            get_logo_path=lambda: None,
        )
        lookup = AddressLookupCoordinator(
            parent_widget=QWidget(),
            search_input=search_input,
            address_form=address_form,
            status_presenter=presenter,
            get_address_parser=lambda: Mock(
                return_value=ParsedAddress(
                    street1="123 Main St", city="Austin", state="TX", zipcode="78701"
                )
            ),
            get_address_completer=lambda: None,
        )

        lookup.load_address()
        del flow

        self.assertEqual(status_label.text(), "Address loaded successfully")
        self.assertIn(STATUS_COLORS["success"], status_label.styleSheet())


if __name__ == "__main__":
    unittest.main()
