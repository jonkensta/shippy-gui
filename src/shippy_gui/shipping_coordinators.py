"""UI coordinators used by the shipping tab."""

# pylint: disable=too-few-public-methods

from dataclasses import dataclass
from typing import Any, Callable, Optional

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtCore import QTimer, Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QApplication,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from shippy_gui.core.addresses import AddressParser
from shippy_gui.core.constants import (
    SHIPMENT_SHUTDOWN_WAIT_MS,
    STATUS_COLORS,
    StatusLevel,
)
from shippy_gui.core.models import AutocompletePrediction, Config
from shippy_gui.core.pending_shipments import PendingShipmentJournal
from shippy_gui.core.refunds import RefundOutcome, RefundPolicy
from shippy_gui.core.services import ShipmentService
from shippy_gui.printing.models import PrintDialogResult
from shippy_gui.printing.printer_manager import print_image_with_dialog
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.autocomplete import GoogleMapsCompleter
from shippy_gui.widgets.shipment_controls import ShipmentControls
from shippy_gui.workers.shipment_worker import ShipmentWorker


@dataclass
class ShippingServices:
    """Mutable holder for runtime services shared with the coordinators.

    ``ShippingTab.reload_config`` rewrites these fields in place after a
    settings save. Coordinators read through the holder, so they are built
    once and never need re-wiring when services are replaced.
    """

    config: Optional[Config] = None
    gmaps: Optional[googlemaps.Client] = None
    address_parser: Optional[AddressParser] = None
    shipment_service: Optional[ShipmentService] = None
    address_completer: Optional[GoogleMapsCompleter] = None
    logo_path: Optional[str] = None
    journal: Optional[PendingShipmentJournal] = None


class ShippingStatusPresenter:
    """Centralized status label formatting for the shipping tab."""

    def __init__(self, status_label: QLabel):
        self._status_label = status_label

    def set_status(self, message: str, level: StatusLevel = StatusLevel.INFO) -> None:
        """Apply a status message and color to the label."""
        color = STATUS_COLORS[level]
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {color}; font-weight: bold;")


class AddressLookupCoordinator:
    """Own address lookup and address form population flow."""

    def __init__(
        self,
        parent_widget: QWidget,
        search_input: QLineEdit,
        address_form: AddressForm,
        status_presenter: ShippingStatusPresenter,
        services: ShippingServices,
    ):
        self._parent_widget = parent_widget
        self._search_input = search_input
        self._address_form = address_form
        self._status_presenter = status_presenter
        self._services = services

    def load_address(self, selected_address: Optional[str] = None) -> None:
        """Parse selected address and populate address fields."""
        search_query = selected_address or self._search_input.text().strip()
        if not search_query:
            self._status_presenter.set_status(
                "Please enter an address to search", StatusLevel.ERROR
            )
            return

        address_parser = self._services.address_parser
        if address_parser is None:
            QMessageBox.critical(
                self._parent_widget, "Error", "Google Maps not configured."
            )
            return

        selected_prediction: Optional[AutocompletePrediction] = None
        completer = self._services.address_completer
        if selected_address and completer:
            selected_prediction = completer.get_prediction_for_text(selected_address)

        self._status_presenter.set_status(
            f"Parsing address: {search_query}...", StatusLevel.INFO
        )

        # AddressParser normalizes Google transport and API failures into None,
        # so a lookup problem and an unparseable address arrive the same way.
        # The guard below is only for genuinely unexpected faults; catching the
        # googlemaps exception types here would be dead code.
        try:
            address_parts = address_parser(selected_prediction or search_query)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._status_presenter.set_status(
                "Address search failed", StatusLevel.ERROR
            )
            QMessageBox.critical(
                self._parent_widget,
                "Address Search Error",
                f"Error parsing address:\n\n{error}",
            )
            return

        if not address_parts:
            self._status_presenter.set_status(
                "Could not parse address", StatusLevel.ERROR
            )
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
                StatusLevel.WARNING,
            )
            return

        self._status_presenter.set_status(
            "Address loaded successfully", StatusLevel.SUCCESS
        )


class ShipmentFlowCoordinator:  # pylint: disable=too-many-instance-attributes
    """Own label creation, worker wiring, and result presentation.

    Refunds use one policy, :class:`RefundPolicy`, bound at purchase time so a
    settings reload cannot redirect a refund to another EasyPost account. The
    background print path applies it inside the worker thread and reports here
    via :meth:`present_refund_outcome`; the print-dialog path applies it here,
    in :meth:`refund_shipment`, because the dialog needs the UI thread.

    The dialog cannot run off the UI thread, so a shipment handed to it is
    resolved only while the app is alive. That gap is covered durably rather
    than in memory: the worker records the purchase in a
    :class:`PendingShipmentJournal` before the hand-off, and anything still
    recorded at the next startup is reconciled with the operator.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        parent_widget: QWidget,
        address_search_input: QLineEdit,
        address_form: AddressForm,
        shipment_controls: ShipmentControls,
        status_presenter: ShippingStatusPresenter,
        services: ShippingServices,
        worker_factory: Callable[..., ShipmentWorker] = ShipmentWorker,
    ):
        self._parent_widget = parent_widget
        self._address_search_input = address_search_input
        self._address_form = address_form
        self._shipment_controls = shipment_controls
        self._status_presenter = status_presenter
        self._services = services
        self._worker_factory = worker_factory
        self.worker: Optional[ShipmentWorker] = None
        # Bound at create_label() to the service that buys the postage, so the
        # dialog path refunds through the same EasyPost account even if
        # settings are reloaded while the label is on screen.
        self._refund_policy: Optional[RefundPolicy] = None

    def create_label(self) -> None:
        """Create and print a shipping label."""
        validation_error = (
            self._address_form.validate_required() or self._shipment_controls.validate()
        )
        if validation_error:
            self._status_presenter.set_status(validation_error, StatusLevel.ERROR)
            return

        shipment_service = self._services.shipment_service
        config = self._services.config
        if shipment_service is None or config is None:
            QMessageBox.critical(
                self._parent_widget, "Error", "Services not configured."
            )
            return

        self._shipment_controls.set_enabled(False)
        self._refund_policy = RefundPolicy(shipment_service)

        use_dialog = (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ) == Qt.KeyboardModifier.ShiftModifier

        self.worker = self._worker_factory(
            shipment_service=shipment_service,
            from_address=config.return_address,
            to_address=self._address_form.get_address(),
            weight_lbs=self._shipment_controls.weight_lbs,
            printer_name=self._shipment_controls.printer_name,
            logo_path=self._services.logo_path,
            use_dialog=use_dialog,
            journal=self._services.journal,
        )

        self.worker.progress.connect(
            lambda message: self._status_presenter.set_status(message, StatusLevel.INFO)
        )
        self.worker.warning.connect(
            lambda message: self._status_presenter.set_status(
                message, StatusLevel.WARNING
            )
        )
        self.worker.success.connect(self._on_shipment_success)
        self.worker.error.connect(self._on_shipment_error)
        self.worker.finished.connect(self._on_shipment_finished)
        self.worker.label_ready.connect(self._on_label_ready)
        self.worker.refunded.connect(self.present_refund_outcome)
        self.worker.start()

    def _on_label_ready(self, image, printer_name: str, shipment: Any) -> None:
        """Handle label ready for printing via system dialog."""
        result = print_image_with_dialog(
            image, self._parent_widget, preferred_printer_name=printer_name
        )
        if result is PrintDialogResult.PRINTED:
            self._resolve_pending(shipment)
            self._on_shipment_success(
                f"Label printed! Tracking: {shipment.tracking_code}"
            )
            return
        if result is PrintDialogResult.CANCELED:
            self.refund_shipment(shipment, "Print canceled")
            return
        self.refund_shipment(shipment, "Print failed")

    def refund_shipment(self, shipment, reason: str) -> None:
        """Refund a shipment whose label was not printed, then present it.

        Used by the print-dialog path, which already runs on the UI thread.
        The background path refunds inside the worker and only calls
        :meth:`present_refund_outcome`.
        """
        if self._refund_policy is None:
            # Never fails silently: unrefunded postage costs real money, so an
            # unreachable state still has to reach the operator.
            self._status_presenter.set_status("Refund failed", StatusLevel.ERROR)
            QMessageBox.critical(
                self._parent_widget,
                "Refund Error",
                f"{reason}, but no refund could be attempted because the "
                "shipment service is unavailable.\n\n"
                f"Please refund shipment {getattr(shipment, 'id', 'unknown')} "
                "manually in EasyPost.",
            )
            return

        self._status_presenter.set_status("Requesting refund...", StatusLevel.WARNING)
        outcome = self._refund_policy.refund(shipment, reason)
        if outcome.refunded:
            self._resolve_pending(shipment)
        self.present_refund_outcome(outcome)

    def _resolve_pending(self, shipment) -> None:
        """Drop a shipment now confirmed printed or refunded."""
        journal = self._services.journal
        if journal is not None:
            journal.clear(getattr(shipment, "id", ""))

    def present_refund_outcome(self, outcome: RefundOutcome) -> None:
        """Report the result of an already-attempted refund."""
        if outcome.refunded:
            self._status_presenter.set_status(
                f"{outcome.reason}. Refunded.", StatusLevel.WARNING
            )
            # The label never came out, so say so in a dialog the operator has
            # to dismiss; a status line is too easy to miss or overwrite.
            QMessageBox.warning(
                self._parent_widget,
                "Label Not Printed",
                f"{outcome.reason}.\n\nThe shipment was refunded. "
                "Nothing was printed, so please try again.",
            )
            return

        self._status_presenter.set_status("Refund failed", StatusLevel.ERROR)
        QMessageBox.critical(
            self._parent_widget,
            "Refund Error",
            f"{outcome.reason}, but the refund did not go through:\n\n{outcome.error}",
        )

    def _on_shipment_success(self, message: str) -> None:
        """Handle successful shipment."""
        self._status_presenter.set_status(message, StatusLevel.SUCCESS)
        # Weight is deliberately left alone: operators usually ship several
        # packages of the same weight in a row.
        self._address_form.clear()
        self._address_search_input.setFocus()

    def _on_shipment_error(self, message: str) -> None:
        """Handle shipment error."""
        self._status_presenter.set_status("Shipment failed", StatusLevel.ERROR)
        QMessageBox.critical(self._parent_widget, "Shipment Error", message)

    def _on_shipment_finished(self) -> None:
        """Handle worker thread completion."""
        self._shipment_controls.set_enabled(True)
        if self.worker is not None:
            # Hand the finished thread to Qt rather than dropping it outright.
            self.worker.deleteLater()
        self.worker = None

    def wait_for_worker(self, timeout_ms: int = SHIPMENT_SHUTDOWN_WAIT_MS) -> bool:
        """Block until any in-flight shipment finishes.

        Called on shutdown. A worker destroyed mid-run aborts the process via
        qFatal, which would strand postage that was bought but not yet
        refunded, so the close is delayed until the thread is done.

        Returns:
            True if no worker is still running afterwards.
        """
        worker = self.worker
        if worker is None or not worker.isRunning():
            return True
        worker.wait(timeout_ms)
        return not worker.isRunning()
