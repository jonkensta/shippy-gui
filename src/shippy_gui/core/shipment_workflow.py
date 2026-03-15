"""Pure shipment workflow orchestration."""

from dataclasses import dataclass
from enum import Enum
import os
from typing import Any, Callable, Optional

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
from PIL import Image

from shippy_gui.core.constants import LOGO_PASTE_X, LOGO_PASTE_Y, OUNCES_PER_POUND
from shippy_gui.core.misc import grab_png_from_url
from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.services import ShipmentService
from shippy_gui.printing.printer_manager import print_image

ProgressCallback = Callable[[str], None]
WarningCallback = Callable[[str], None]


class ShipmentWorkflowStatus(str, Enum):
    """High-level workflow result statuses."""

    READY = "ready"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ShipmentWorkflowResult:
    """Typed workflow result used by the worker and UI adapters."""

    status: ShipmentWorkflowStatus
    message: str
    shipment: Optional[Any] = None
    image: Optional[Image.Image] = None
    refund_requested: bool = False


@dataclass(frozen=True)
class ShipmentWorkflowInput:
    """Input model for shipment workflow preparation."""

    from_address: ReturnAddressConfig
    to_address: RecipientAddress
    weight_lbs: int
    logo_path: Optional[str] = None


class ShipmentWorkflow:  # pylint: disable=too-few-public-methods
    """Orchestrate shipment creation, label preparation, and quick printing."""

    def __init__(self, shipment_service: ShipmentService):
        self.service = shipment_service

    def prepare_label(
        self,
        workflow_input: ShipmentWorkflowInput,
        on_progress: Optional[ProgressCallback] = None,
        on_warning: Optional[WarningCallback] = None,
    ) -> ShipmentWorkflowResult:
        """Create a shipment and prepare its label image."""
        progress = on_progress or (lambda _message: None)
        warning = on_warning or (lambda _message: None)

        try:
            progress("Building return address...")
            from_addr = self.service.create_address(workflow_input.from_address)

            try:
                progress("Verifying return address...")
                self.service.verify_address(from_addr.id)
            except easypost.errors.InvalidRequestError:
                warning(
                    "Failed to verify return address. Please check your config.ini."
                )

            progress("Building recipient address...")
            to_addr = self.service.create_address(workflow_input.to_address)

            try:
                progress("Verifying recipient address...")
                self.service.verify_address(to_addr.id)
            except easypost.errors.InvalidRequestError:
                warning(
                    "Failed to verify recipient address. Please double-check before shipping."
                )

            progress("Purchasing postage...")
            weight_oz = workflow_input.weight_lbs * OUNCES_PER_POUND
            shipment = self.service.buy_shipment(from_addr.id, to_addr.id, weight_oz)

            progress("Downloading label...")
            label_url = shipment.postage_label.label_url
            image = grab_png_from_url(label_url)

            if workflow_input.logo_path and os.path.exists(workflow_input.logo_path):
                progress("Adding logo...")
                logo = Image.open(workflow_input.logo_path)
                image.paste(logo, (LOGO_PASTE_X, LOGO_PASTE_Y))

            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.READY,
                message="Label prepared successfully",
                shipment=shipment,
                image=image,
            )

        except easypost.errors.ApiError as error:
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"Shipment creation failed: EasyPost API error: {error}",
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"Shipment creation failed: Unexpected error: {error}",
            )

    def print_prepared_label(
        self,
        prepared_result: ShipmentWorkflowResult,
        printer_name: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ShipmentWorkflowResult:
        """Print a prepared label image and request a refund on failure."""
        progress = on_progress or (lambda _message: None)

        if not prepared_result.shipment or prepared_result.image is None:
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message="Shipment creation failed: No prepared label available.",
            )

        try:
            progress("Printing label...")
            print_image(prepared_result.image, printer_name)
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.SUCCESS,
                message=(
                    "Label printed successfully! "
                    f"Tracking: {prepared_result.shipment.tracking_code}"
                ),
                shipment=prepared_result.shipment,
                image=prepared_result.image,
            )
        except RuntimeError as error:
            return self.refund_after_failure(
                prepared_result.shipment,
                f"Printing error: {error}",
                on_progress=progress,
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            return self.refund_after_failure(
                prepared_result.shipment,
                f"Unexpected error: {error}",
                on_progress=progress,
            )

    def refund_after_failure(
        self,
        shipment,
        error_message: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ShipmentWorkflowResult:
        """Request a refund for a failed shipment operation."""
        progress = on_progress or (lambda _message: None)

        try:
            progress("Requesting refund...")
            self.service.refund_shipment(shipment.id)
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"{error_message}. Refund requested.",
                shipment=shipment,
                refund_requested=True,
            )
        except easypost.errors.ApiError as refund_error:
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"{error_message}. Refund also failed: {refund_error}",
                shipment=shipment,
            )
        except Exception as refund_error:  # pylint: disable=broad-exception-caught
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"{error_message}. Refund also failed: {refund_error}",
                shipment=shipment,
            )
