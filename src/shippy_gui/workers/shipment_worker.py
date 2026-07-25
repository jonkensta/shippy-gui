"""Worker thread for creating and printing shipping labels."""

from typing import Optional

from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.pending_shipments import PendingShipmentJournal
from shippy_gui.core.refunds import RefundPolicy
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.shipment_workflow import (
    ShipmentPreparationError,
    ShipmentWorkflow,
    ShipmentWorkflowInput,
)
from shippy_gui.printing.printer_manager import print_image


class ShipmentWorker(QThread):  # pylint: disable=too-few-public-methods
    """Worker thread for async shipment creation and printing.

    Printing and, when it fails, the refund both happen here, inside
    :meth:`run`, so that neither depends on the UI thread still being alive.
    The coordinator is only told the outcome, via ``refunded``.

    The print-dialog path is the exception: the dialog is inherently a UI
    affair, so ``label_ready`` hands off to the coordinator, which owns the
    refund for that path using a policy bound at purchase time.
    """

    # Signals
    progress = Signal(str)  # Progress message
    success = Signal(str)  # Success message
    error = Signal(str)  # Error message
    warning = Signal(str)  # Warning message (non-blocking)
    label_ready = Signal(object, str, object)  # (image, printer_name, shipment_object)
    refunded = Signal(object)  # RefundOutcome, already applied

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        shipment_service: ShipmentService,
        from_address: ReturnAddressConfig,
        to_address: RecipientAddress,
        weight_lbs: int,
        printer_name: str,
        logo_path: Optional[str] = None,
        use_dialog: bool = False,
        journal: Optional[PendingShipmentJournal] = None,
    ):
        """Initialize the shipment worker.

        Args:
            shipment_service: Shipment logic service
            from_address: Return address model
            to_address: Recipient address model
            weight_lbs: Package weight in pounds
            printer_name: Name of printer to use
            logo_path: Optional path to logo image to overlay
            use_dialog: Whether to use system print dialog (default: False)
            journal: Optional durable record of purchased postage, used to
                reconcile a shipment if the app dies before it is printed
                or refunded.
        """
        super().__init__()
        self.workflow = ShipmentWorkflow(shipment_service)
        # Bound to the service that buys the postage, so a settings reload
        # mid-shipment cannot refund against a different EasyPost account.
        self.refund_policy = RefundPolicy(shipment_service)
        self.workflow_input = ShipmentWorkflowInput(
            from_address=from_address,
            to_address=to_address,
            weight_lbs=weight_lbs,
            logo_path=logo_path,
        )
        self.printer_name = printer_name
        self.use_dialog = use_dialog
        self.journal = journal
        self.shipment = None

    def run(self):
        """Create the shipment, then print it or hand it to the print dialog."""
        try:
            prepared = self.workflow.prepare_label(
                self.workflow_input,
                on_progress=self.progress.emit,
                on_warning=self.warning.emit,
                on_purchase=self._record_pending,
            )
        except ShipmentPreparationError as error:
            if error.shipment is not None:
                # Postage was already bought before this failed; refund it
                # rather than reporting a failure the operator would ignore.
                self.shipment = error.shipment
                self._refund(error.shipment, str(error))
                return
            self.error.emit(f"Shipment creation failed: {error}")
            return

        self.shipment = prepared.shipment

        if self.use_dialog:
            self.label_ready.emit(prepared.image, self.printer_name, prepared.shipment)
            return

        self.progress.emit("Printing label...")
        try:
            print_image(prepared.image, self.printer_name)
        except RuntimeError as error:
            self._refund(prepared.shipment, f"Printing error: {error}")
            return
        except Exception as error:  # pylint: disable=broad-exception-caught
            self._refund(prepared.shipment, f"Unexpected printing error: {error}")
            return

        self._resolve_pending(prepared.shipment)
        self.success.emit(
            "Label printed successfully! "
            f"Tracking: {prepared.shipment.tracking_code}"
        )

    def _record_pending(self, shipment) -> None:
        """Note bought postage whose outcome is not yet known.

        Called by the workflow the instant postage is bought. A failure here
        means the shipment cannot be recovered automatically, so it is said
        out loud rather than swallowed.
        """
        if self.journal is None:
            return
        shipment_id = getattr(shipment, "id", "")
        recorded = self.journal.record(
            shipment_id,
            tracking_code=getattr(shipment, "tracking_code", None),
        )
        if not recorded:
            self.warning.emit(
                f"Could not record shipment {shipment_id} locally. "
                "If this label does not print, refund it manually in EasyPost."
            )

    def _resolve_pending(self, shipment) -> None:
        """Drop a shipment that is now confirmed printed or refunded."""
        if self.journal is None:
            return
        self.journal.clear(getattr(shipment, "id", ""))

    def _refund(self, shipment, reason: str) -> None:
        """Refund a shipment that failed to print.

        The refund runs here, inside the worker thread, rather than being
        delegated to the UI through a queued signal: it must survive the
        window closing between the failure and the next event-loop turn.
        The UI is notified of the outcome afterwards, for display only.
        """
        self.progress.emit("Requesting refund...")
        outcome = self.refund_policy.refund(shipment, reason)
        if outcome.refunded:
            self._resolve_pending(shipment)
        self.refunded.emit(outcome)
