"""UI coordinators used by the shipping tab."""

# pylint: disable=too-few-public-methods

import logging
from typing import Any, Callable, Optional, Sequence

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtCore import QTimer, Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from shippy_gui.core import label_journal
from shippy_gui.core.addresses import AddressParser
from shippy_gui.core.constants import STATUS_COLORS
from shippy_gui.core.models import AutocompletePrediction, Config, RecipientAddress
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.shipment_workflow import (
    ShipmentWorkflow,
    ShipmentWorkflowResult,
    dialog_uncertain_warning,
)
from shippy_gui.printing.printer_manager import (
    DialogPrintStatus,
    print_image_with_dialog,
)
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.autocomplete import GoogleMapsCompleter
from shippy_gui.widgets.label_queue import confirm_duplicate_label, show_label_queued
from shippy_gui.widgets.shipment_controls import ShipmentControls
from shippy_gui.workers.shipment_worker import ShipmentWorker

logger = logging.getLogger(__name__)


class ShippingStatusPresenter:
    """Centralized status label formatting for the shipping tab."""

    def __init__(self, status_label: QLabel):
        self._status_label = status_label

    def set_status(self, message: str, status_type: str = "info") -> None:
        """Apply a status message and color to the label."""
        color = STATUS_COLORS.get(status_type, STATUS_COLORS["info"])
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {color}; font-weight: bold;")


class AddressLookupCoordinator:
    """Own address lookup and address form population flow."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        parent_widget: QWidget,
        search_input: QLineEdit,
        address_form: AddressForm,
        status_presenter: ShippingStatusPresenter,
        get_address_parser: Callable[[], Optional[AddressParser]],
        get_address_completer: Callable[[], Optional[GoogleMapsCompleter]],
    ):
        self._parent_widget = parent_widget
        self._search_input = search_input
        self._address_form = address_form
        self._status_presenter = status_presenter
        self._get_address_parser = get_address_parser
        self._get_address_completer = get_address_completer

    def load_address(self, selected_address: Optional[str] = None) -> None:
        """Parse selected address and populate address fields."""
        search_query = selected_address or self._search_input.text().strip()
        if not search_query:
            self._status_presenter.set_status(
                "Please enter an address to search", "error"
            )
            return

        address_parser = self._get_address_parser()
        if address_parser is None:
            QMessageBox.critical(
                self._parent_widget, "Error", "Google Maps not configured."
            )
            return

        selected_prediction: Optional[AutocompletePrediction] = None
        completer = self._get_address_completer()
        if selected_address and completer:
            selected_prediction = completer.get_prediction_for_text(selected_address)

        self._status_presenter.set_status(f"Parsing address: {search_query}...", "info")

        try:
            address_parts = address_parser(selected_prediction or search_query)
            if not address_parts:
                self._status_presenter.set_status("Could not parse address", "error")
                QMessageBox.warning(
                    self._parent_widget,
                    "Address Parse Error",
                    f"Could not parse the selected address:\n\n{search_query}\n\n"
                    "Please try a different address or enter manually.",
                )
                return

            self._address_form.merge_address(address_parts)
            QTimer.singleShot(0, self._search_input.clear)

            missing = AddressForm.missing_required_keys(address_parts)
            if missing:
                self._status_presenter.set_status(
                    f"Address incomplete - missing: {', '.join(missing)}",
                    "warning",
                )
                return

            self._status_presenter.set_status("Address loaded successfully", "success")
        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ) as error:
            self._status_presenter.set_status("Address search failed", "error")
            QMessageBox.critical(
                self._parent_widget,
                "Address Search Error",
                f"Google Maps API error:\n\n{error}",
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._status_presenter.set_status("Address search failed", "error")
            QMessageBox.critical(
                self._parent_widget,
                "Address Search Error",
                f"Error parsing address:\n\n{error}",
            )


class ShipmentFlowCoordinator:  # pylint: disable=too-many-instance-attributes
    """Own label creation, worker wiring, and result presentation."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        parent_widget: QWidget,
        address_search_input: QLineEdit,
        address_form: AddressForm,
        shipment_controls: ShipmentControls,
        status_presenter: ShippingStatusPresenter,
        get_config: Callable[[], Optional[Config]],
        get_shipment_service: Callable[[], Optional[ShipmentService]],
        get_logo_path: Callable[[], Optional[str]],
        worker_factory: Callable[..., ShipmentWorker] = ShipmentWorker,
        find_duplicates: Callable[
            [label_journal.LabelIdentity], Sequence[Any]
        ] = label_journal.find_duplicates,
        confirm_duplicate: Callable[
            [QWidget, Sequence[Any]], bool
        ] = confirm_duplicate_label,
        on_shipment_done: Optional[Callable[[], None]] = None,
    ):
        self._parent_widget = parent_widget
        self._address_search_input = address_search_input
        self._address_form = address_form
        self._shipment_controls = shipment_controls
        self._status_presenter = status_presenter
        self._get_config = get_config
        self._get_shipment_service = get_shipment_service
        self._get_logo_path = get_logo_path
        self._worker_factory = worker_factory
        self._find_duplicates = find_duplicates
        self._confirm_duplicate = confirm_duplicate
        self._on_shipment_done = on_shipment_done or (lambda: None)
        self.worker: Optional[ShipmentWorker] = None

    def create_label(self) -> None:
        """Create and print a shipping label."""
        validation_error = (
            self._address_form.validate_required() or self._shipment_controls.validate()
        )
        if validation_error:
            self._status_presenter.set_status(validation_error, "error")
            return

        shipment_service = self._get_shipment_service()
        config = self._get_config()
        if shipment_service is None or config is None:
            QMessageBox.critical(
                self._parent_widget, "Error", "Services not configured."
            )
            return

        # Read Shift before any question box can change the modifier state.
        use_dialog = (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ) == Qt.KeyboardModifier.ShiftModifier

        to_address = self._address_form.get_address()
        if not self._confirm_not_duplicate(to_address):
            return

        self._shipment_controls.set_enabled(False)

        self.worker = self._worker_factory(
            shipment_service=shipment_service,
            from_address=config.return_address,
            to_address=to_address,
            weight_lbs=self._shipment_controls.weight_lbs,
            printer_name=self._shipment_controls.printer_name,
            logo_path=self._get_logo_path(),
            use_dialog=use_dialog,
        )

        self.worker.progress.connect(
            lambda message: self._status_presenter.set_status(message, "info")
        )
        self.worker.warning.connect(
            lambda message: self._status_presenter.set_status(message, "warning")
        )
        self.worker.success.connect(self._on_shipment_success)
        self.worker.success_with_warning.connect(self._on_shipment_success_with_warning)
        self.worker.label_saved.connect(self._on_label_saved)
        self.worker.error.connect(self._on_shipment_error)
        self.worker.finished.connect(self._on_shipment_finished)
        self.worker.label_ready.connect(self._on_label_ready)
        self.worker.start()

    def _confirm_not_duplicate(self, to_address: RecipientAddress) -> bool:
        """Stop before buying postage when this recipient already has a label.

        Returns True to go ahead. The volunteer must explicitly answer Yes to
        create another label; the journal being unavailable never blocks.
        """
        try:
            identity = label_journal.identity_for(to_address)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Could not build the label journal key; not checking")
            return True
        records = list(self._find_duplicates(identity))
        if not records:
            return True

        trackings = ", ".join(str(record.tracking_code) for record in records)
        create = self._confirm_duplicate(self._parent_widget, records)
        logger.warning(
            "Possible duplicate label for %s (existing: %s): volunteer chose %s",
            identity.recipient_label,
            trackings,
            "to create another label" if create else "NOT to create another label",
        )
        if not create:
            self._status_presenter.set_status(
                f"Label NOT created: {identity.recipient_label} already has one "
                f"(tracking {trackings})",
                "warning",
            )
        return create

    def _on_label_ready(
        self,
        image,
        printer_name: str,
        shipment: Any,
        prepared: Optional[ShipmentWorkflowResult] = None,
    ) -> None:
        """Handle label ready for printing via system dialog.

        Canceled: refund (nothing was printed and the volunteer chose not to).
        Not sent (printing could not start): save for the label watcher like
        a PrintError, refunding only if saving fails. Failed after printing
        started: warn, no refund, nothing saved.
        """
        result = print_image_with_dialog(
            image, self._parent_widget, preferred_printer_name=printer_name
        )
        if result == DialogPrintStatus.PRINTED:
            label_journal.update_status(shipment, label_journal.STATUS_PRINTED)
            self._on_shipment_success(
                f"Label printed! Tracking: {shipment.tracking_code}"
            )
        elif result == DialogPrintStatus.CANCELED:
            self._refund_shipment(shipment, "Print canceled")
        elif result == DialogPrintStatus.NOT_SENT:
            self._save_dialog_label(image, printer_name, shipment, prepared)
        else:
            label_journal.update_status(shipment, label_journal.STATUS_CHECK_PRINTER)
            self._on_shipment_success_with_warning(
                f"{dialog_uncertain_warning()} Tracking: {shipment.tracking_code}"
            )
        # The worker may have finished while the print dialog was open.
        self._on_shipment_done()

    def _save_dialog_label(
        self,
        image,
        printer_name: str,
        shipment: Any,
        prepared: Optional[ShipmentWorkflowResult] = None,
    ) -> None:
        """Queue a dialog-printed label that never started printing."""
        shipment_service = self._get_shipment_service()
        if shipment_service is None:
            self._on_shipment_error(
                "The label did not print and could not be saved: services "
                f"not configured. Tracking: {shipment.tracking_code}"
            )
            return
        result = ShipmentWorkflow(shipment_service).save_unprinted_label(
            shipment,
            image,
            RuntimeError(
                f"printing could not start on {printer_name or 'the printer'}"
            ),
            on_progress=lambda message: self._status_presenter.set_status(
                message, "info"
            ),
            identity=prepared.identity if prepared else None,
            label_record=prepared.label_record if prepared else None,
        )
        if result.saved_label_path is not None:
            self._on_label_saved(result)
        else:
            self._on_shipment_error(result.message)

    def _refund_shipment(self, shipment, reason: str) -> None:
        """Request a refund for a shipment."""
        shipment_service = self._get_shipment_service()
        if shipment_service is None:
            return

        self._status_presenter.set_status("Requesting refund...", "warning")
        try:
            shipment_service.refund_shipment(shipment.id)
            label_journal.update_status(shipment, label_journal.STATUS_REFUNDED)
            self._status_presenter.set_status(f"{reason}. Refunded.", "warning")
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._status_presenter.set_status("Refund failed", "error")
            QMessageBox.critical(self._parent_widget, "Refund Error", str(error))

    def _on_shipment_success(self, message: str) -> None:
        """Handle successful shipment."""
        self._status_presenter.set_status(message, "success")
        self._address_form.clear()
        self._shipment_controls.reset()
        self._address_search_input.setFocus()

    def _on_shipment_success_with_warning(self, message: str) -> None:
        """Handle a label that was spooled but may not have printed."""
        self._on_shipment_success(message)
        self._status_presenter.set_status(message, "warning")
        QMessageBox.warning(self._parent_widget, "Check The Printer", message)

    def _on_label_saved(self, result: ShipmentWorkflowResult) -> None:
        """Handle a label that did not print and was saved for printing later."""
        # Postage is kept, so clear the form like a success: re-submitting it
        # would buy a second label.
        self._on_shipment_success(result.message)
        recipient = (
            result.identity.recipient_label if result.identity else "this recipient"
        )
        tracking = (
            label_journal.tracking_ref(result.shipment) if result.shipment else "?"
        )
        self._status_presenter.set_status(
            f"Label QUEUED for {recipient} (tracking {tracking}) - it will print "
            "automatically. Do NOT create it again.",
            "warning",
        )
        show_label_queued(self._parent_widget, recipient, tracking, result.message)

    def _on_shipment_error(self, message: str) -> None:
        """Handle shipment error."""
        self._status_presenter.set_status("Shipment failed", "error")
        QMessageBox.critical(self._parent_widget, "Shipment Error", message)

    def _on_shipment_finished(self) -> None:
        """Handle worker thread completion."""
        self._shipment_controls.set_enabled(True)
        self.worker = None
        self._on_shipment_done()
