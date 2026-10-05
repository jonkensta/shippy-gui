"""Pure shipment workflow orchestration."""

from dataclasses import dataclass
from enum import Enum
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
import ibp_printing
from PIL import Image

from shippy_gui.core import label_journal
from shippy_gui.core.constants import (
    LOGO_PASTE_X,
    LOGO_PASTE_Y,
    OUNCES_PER_POUND,
    PRINT_JOB_NAME,
)
from shippy_gui.core.misc import grab_png_from_url
from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.services import ShipmentService
from shippy_gui.printing.printer_manager import print_image

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]
WarningCallback = Callable[[str], None]


class ShipmentWorkflowStatus(str, Enum):
    """High-level workflow result statuses."""

    READY = "ready"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class ShipmentWorkflowResult:  # pylint: disable=too-many-instance-attributes
    """Typed workflow result used by the worker and UI adapters."""

    status: ShipmentWorkflowStatus
    message: str
    shipment: Optional[Any] = None
    image: Optional[Image.Image] = None
    refund_requested: bool = False
    # Set when the label was spooled (so no refund) but the print queue then
    # reported a bad outcome; the UI must show it prominently.
    print_warning: Optional[str] = None
    # Set when no printer could take the label: it was saved to the print
    # queue folder instead (postage NOT refunded); the UI must show it.
    saved_label_path: Optional[Path] = None
    # Who the label is for, as the shared label journal knows it.
    identity: Optional[label_journal.LabelIdentity] = None
    # The journal record made when postage was bought (None if not journaled).
    label_record: Optional[Any] = None


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

    def prepare_label(  # pylint: disable=too-many-locals
        self,
        workflow_input: ShipmentWorkflowInput,
        on_progress: Optional[ProgressCallback] = None,
        on_warning: Optional[WarningCallback] = None,
    ) -> ShipmentWorkflowResult:
        """Create a shipment and prepare its label image."""
        progress = on_progress or (lambda _message: None)
        warning = on_warning or (lambda _message: None)

        shipment = None
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

            identity = label_journal.identity_for(workflow_input.to_address)

            progress("Purchasing postage...")
            weight_oz = workflow_input.weight_lbs * OUNCES_PER_POUND
            shipment = self.service.buy_shipment(from_addr.id, to_addr.id, weight_oz)
            record = label_journal.record_purchase(identity, shipment)

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
                identity=identity,
                label_record=record,
            )

        except easypost.errors.ApiError as error:
            message = f"EasyPost API error: {error}"
        except Exception as error:  # pylint: disable=broad-exception-caught
            message = f"Unexpected error: {error}"

        if shipment is None:
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message=f"Shipment creation failed: {message}",
            )
        # Postage was bought but there is no label image to print or save.
        logger.error("Label preparation failed after purchase: %s", message)
        return self.refund_after_failure(
            shipment,
            f"Label could not be prepared after buying postage: {message}",
            on_progress=progress,
        )

    def print_prepared_label(
        self,
        prepared_result: ShipmentWorkflowResult,
        printer_name: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ShipmentWorkflowResult:
        """Print a prepared label image.

        Never refunds once printing was attempted, except when the label
        definitely reached no printer AND could not be saved for the label
        watcher (see ``save_unprinted_label``).
        """
        progress = on_progress or (lambda _message: None)

        if not prepared_result.shipment or prepared_result.image is None:
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.ERROR,
                message="Shipment creation failed: No prepared label available.",
            )
        shipment, image = prepared_result.shipment, prepared_result.image
        journal: dict[str, Any] = {
            "identity": prepared_result.identity,
            "label_record": prepared_result.label_record,
        }

        try:
            progress("Printing label...")
            print_result = print_image(
                image,
                printer_name,
                job_name=f"{PRINT_JOB_NAME} {shipment.tracking_code}",
            )
        except ibp_printing.PrintError as error:
            # The job definitely never reached a printer. Keep the postage and
            # queue the label for the label watcher instead of refunding.
            return self.save_unprinted_label(
                shipment, image, error, on_progress=progress, **journal
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            # Not a PrintError: whether the job reached the spooler is unknown,
            # so treat it as uncertain (no refund, no automatic retry).
            logger.exception("Unexpected error while printing %s", shipment.id)
            label_journal.update_status(shipment, label_journal.STATUS_CHECK_PRINTER)
            warning = print_raised_warning(printer_name, error)
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.SUCCESS,
                message=f"{warning} Tracking: {_shipment_ref(shipment)}",
                shipment=shipment,
                image=image,
                print_warning=warning,
                **journal,
            )

        # The job was spooled; nothing below may refund.
        tracking = shipment.tracking_code
        if not print_result.outcome.ok:
            label_journal.update_status(shipment, label_journal.STATUS_CHECK_PRINTER)
            warning = _print_outcome_warning(printer_name, print_result)
            return ShipmentWorkflowResult(
                status=ShipmentWorkflowStatus.SUCCESS,
                message=f"{warning} Tracking: {tracking}",
                shipment=shipment,
                image=image,
                print_warning=warning,
                **journal,
            )
        label_journal.update_status(shipment, label_journal.STATUS_PRINTED)
        return ShipmentWorkflowResult(
            status=ShipmentWorkflowStatus.SUCCESS,
            message=f"Label printed successfully! Tracking: {tracking}",
            shipment=shipment,
            image=image,
            **journal,
        )

    def save_unprinted_label(  # pylint: disable=too-many-arguments
        self,
        shipment: Any,
        image: Image.Image,
        print_error: Exception,
        on_progress: Optional[ProgressCallback] = None,
        *,
        identity: Optional[label_journal.LabelIdentity] = None,
        label_record: Optional[Any] = None,
    ) -> ShipmentWorkflowResult:
        """Save an unprinted label to the print queue; refund only if that fails."""
        progress = on_progress or (lambda _message: None)
        tracking = _shipment_ref(shipment)
        try:
            progress("Saving label to print later...")
            path = ibp_printing.save_for_retry(
                image,
                name=tracking,
                meta=label_journal.retry_meta(identity, shipment, label_record),
            )
        except Exception as save_error:  # pylint: disable=broad-exception-caught
            logger.exception("Could not save unprinted label %s", tracking)
            return self.refund_after_failure(
                shipment,
                f"Printing error: {print_error}. The label also could not be "
                f"saved to print later: {save_error}",
                on_progress=progress,
            )

        # Outside the refund context: the label is queued and may print soon.
        label_journal.update_status(shipment, label_journal.STATUS_QUEUED, file=path)
        warning = saved_label_message(print_error, path)
        return ShipmentWorkflowResult(
            status=ShipmentWorkflowStatus.SUCCESS,
            message=f"{warning}\n\nTracking: {tracking}",
            shipment=shipment,
            image=image,
            saved_label_path=path,
            identity=identity,
            label_record=label_record,
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
            label_journal.update_status(shipment, label_journal.STATUS_REFUNDED)
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


def _shipment_ref(shipment: Any) -> str:
    """What a volunteer searches for in EasyPost: tracking code, else id."""
    return shipment.tracking_code or shipment.id


def saved_label_message(print_error: Exception, path: Path) -> str:
    """Tell the volunteer an unprinted label was queued and postage kept."""
    return (
        f"The label did NOT print: {print_error}\n\n"
        f"It was saved to:\n{path}\n\n"
        "If the IBP label watcher is running, it will print automatically as "
        "soon as a label printer is working.\n\n"
        "Postage was NOT refunded.\n\n"
        "Before you print that file by hand, or refund this shipment in "
        f"EasyPost, DELETE it from {path.parent} first, so the label watcher "
        "does not print it too. If it is already gone, the watcher has picked "
        "it up: check the printer (and the printed and check-printer folders "
        "next to it) before doing either."
    )


def print_raised_warning(printer_name: str, error: Exception) -> str:
    """Explain an unexpected print error after which the label may still print."""
    return (
        f"Printing to {printer_name} failed unexpectedly ({error}) after the "
        "label may already have reached the printer. It may or may NOT have "
        "printed - check the printer before reprinting; postage was NOT "
        f"refunded. Printer logs: {ibp_printing.default_log_dir()}"
    )


def dialog_uncertain_warning() -> str:
    """Explain a print-dialog job that failed after printing had started."""
    return (
        "Printing through the print dialog failed after it had started. The "
        "label may or may NOT have printed - check the printer before "
        "reprinting; postage was NOT refunded."
    )


# Outcomes whose raw value reads badly in a sentence about "the print queue".
_OUTCOME_DETAILS = {
    "uncertain": "it could not be confirmed that the job reached the printer",
    "tracking_failed": "following the print job failed",
}


def _print_outcome_warning(
    printer_name: str, print_result: ibp_printing.PrintResult
) -> str:
    """Explain a spooled job whose tracked outcome suggests no label came out."""
    outcome = print_result.outcome.value
    detail = _OUTCOME_DETAILS.get(outcome, f"the print queue reported '{outcome}'")
    return (
        f"Label was sent to {printer_name} but {detail}. It may NOT have "
        "printed - check the printer before reprinting; postage was NOT "
        f"refunded. Printer logs: {ibp_printing.default_log_dir()}"
    )
