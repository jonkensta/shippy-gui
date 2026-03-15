"""Worker thread for creating and printing shipping labels."""

import os
from typing import Optional

from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.shipment_workflow import (
    ShipmentWorkflowInput,
    ShipmentWorkflow,
    ShipmentWorkflowStatus,
)


class ShipmentWorker(
    QThread
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Worker thread for async shipment creation and printing."""

    # Signals
    progress = Signal(str)  # Progress message
    success = Signal(str)  # Success message
    error = Signal(str)  # Error message
    warning = Signal(str)  # Warning message (non-blocking)
    label_ready = Signal(object, str, object)  # (image, printer_name, shipment_object)

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
        self.from_address = from_address
        self.to_address = to_address
        self.weight_lbs = weight_lbs
        self.printer_name = printer_name
        self.logo_path = logo_path
        self.use_dialog = use_dialog
        self.shipment = None

    def run(self):
        """Execute the shipment workflow."""
        prepared_result = self.workflow.prepare_label(
            ShipmentWorkflowInput(
                from_address=self.from_address,
                to_address=self.to_address,
                weight_lbs=self.weight_lbs,
                logo_path=(
                    self.logo_path
                    if self.logo_path and os.path.exists(self.logo_path)
                    else None
                ),
            ),
            on_progress=self.progress.emit,
            on_warning=self.warning.emit,
        )

        if prepared_result.status is ShipmentWorkflowStatus.ERROR:
            self.error.emit(prepared_result.message)
            return

        self.shipment = prepared_result.shipment
        if self.use_dialog:
            self.label_ready.emit(
                prepared_result.image, self.printer_name, self.shipment
            )
            return

        print_result = self.workflow.print_prepared_label(
            prepared_result=prepared_result,
            printer_name=self.printer_name,
            on_progress=self.progress.emit,
        )
        if print_result.status is ShipmentWorkflowStatus.SUCCESS:
            self.success.emit(print_result.message)
            return

        self.error.emit(print_result.message)
