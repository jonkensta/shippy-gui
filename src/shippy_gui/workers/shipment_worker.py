"""Worker thread for creating and printing shipping labels."""

from typing import Optional

from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.shipment_workflow import (
    ShipmentPreparationError,
    ShipmentWorkflow,
    ShipmentWorkflowInput,
)
from shippy_gui.printing.printer_manager import print_image


class ShipmentWorker(QThread):  # pylint: disable=too-few-public-methods
    """Worker thread for async shipment creation and printing.

    Printing happens here so it stays off the UI thread. Refunds do not: a
    failed print is reported via ``print_failed`` and the coordinator owns the
    single refund policy shared with the print-dialog path.
    """

    # Signals
    progress = Signal(str)  # Progress message
    success = Signal(str)  # Success message
    error = Signal(str)  # Error message
    warning = Signal(str)  # Warning message (non-blocking)
    label_ready = Signal(object, str, object)  # (image, printer_name, shipment_object)
    print_failed = Signal(object, str)  # (shipment_object, reason)

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        shipment_service: ShipmentService,
        from_address: ReturnAddressConfig,
        to_address: RecipientAddress,
        weight_lbs: int,
        printer_name: str,
        logo_path: Optional[str] = None,
        use_dialog: bool = False,
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
        """
        super().__init__()
        self.workflow = ShipmentWorkflow(shipment_service)
        self.workflow_input = ShipmentWorkflowInput(
            from_address=from_address,
            to_address=to_address,
            weight_lbs=weight_lbs,
            logo_path=logo_path,
        )
        self.printer_name = printer_name
        self.use_dialog = use_dialog
        self.shipment = None

    def run(self):
        """Create the shipment, then print it or hand it to the print dialog."""
        try:
            prepared = self.workflow.prepare_label(
                self.workflow_input,
                on_progress=self.progress.emit,
                on_warning=self.warning.emit,
            )
        except ShipmentPreparationError as error:
            self.error.emit(f"Shipment creation failed: {error}")
            return

        self.shipment = prepared.shipment

        if self.use_dialog:
            self.label_ready.emit(prepared.image, self.printer_name, prepared.shipment)
            return

        self.progress.emit("Printing label...")
        try:
            print_image(prepared.image, self.printer_name)
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.print_failed.emit(prepared.shipment, f"Printing error: {error}")
            return

        self.success.emit(
            "Label printed successfully! "
            f"Tracking: {prepared.shipment.tracking_code}"
        )
