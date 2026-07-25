"""Shipment creation and label preparation.

This module is deliberately free of Qt and of printing concerns: importing it
must not pull in a GUI toolkit. Printing is performed by ``workers`` (off the
UI thread) and refunds are owned by ``shipping_coordinators``, so that the
"refund a shipment whose label did not print" policy exists in exactly one
place regardless of which print path was taken.
"""

from dataclasses import dataclass
import os
from typing import Any, Callable, Optional

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
from PIL import Image

from shippy_gui.core.constants import LOGO_PASTE_X, LOGO_PASTE_Y, OUNCES_PER_POUND
from shippy_gui.core.misc import grab_png_from_url
from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.services import ShipmentService

ProgressCallback = Callable[[str], None]
WarningCallback = Callable[[str], None]


class ShipmentPreparationError(Exception):
    """Raised when a shipment could not be created or its label prepared.

    The message describes the cause only. Callers add any user-facing framing,
    which keeps presentation copy out of ``core``.

    Attributes:
        shipment: The purchased shipment when the failure happened *after*
            postage was bought, otherwise None. Postage is bought before the
            label is downloaded and stamped, so those later steps can fail with
            money already spent - callers must refund whenever this is set.
    """

    def __init__(self, message: str, shipment: Any = None):
        super().__init__(message)
        self.shipment = shipment


@dataclass(frozen=True)
class ShipmentWorkflowInput:
    """Input model for shipment workflow preparation."""

    from_address: ReturnAddressConfig
    to_address: RecipientAddress
    weight_lbs: int
    logo_path: Optional[str] = None


@dataclass(frozen=True)
class PreparedLabel:
    """A purchased shipment and its ready-to-print label image."""

    shipment: Any
    image: Image.Image


class ShipmentWorkflow:  # pylint: disable=too-few-public-methods
    """Create a shipment and prepare its label image."""

    def __init__(self, shipment_service: ShipmentService):
        self.service = shipment_service

    def prepare_label(
        self,
        workflow_input: ShipmentWorkflowInput,
        on_progress: Optional[ProgressCallback] = None,
        on_warning: Optional[WarningCallback] = None,
    ) -> PreparedLabel:
        """Create a shipment, buy postage, and build the label image.

        Args:
            workflow_input: Addresses, weight, and optional logo overlay.
            on_progress: Optional sink for progress messages.
            on_warning: Optional sink for non-fatal warnings.

        Returns:
            The purchased shipment and its label image.

        Raises:
            ShipmentPreparationError: If the shipment or label could not be
                prepared.
        """
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
        except easypost.errors.ApiError as error:
            raise ShipmentPreparationError(f"EasyPost API error: {error}") from error
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise ShipmentPreparationError(f"Unexpected error: {error}") from error

        # Past this point money has been spent. Every failure below has to
        # carry the shipment so the caller can refund it.
        try:
            progress("Downloading label...")
            label_url = shipment.postage_label.label_url
            image = grab_png_from_url(label_url)

            if workflow_input.logo_path and os.path.exists(workflow_input.logo_path):
                progress("Adding logo...")
                with Image.open(workflow_input.logo_path) as logo:
                    # Pillow clips a paste that runs off the canvas, so an
                    # unexpectedly small label loses the logo, not the print.
                    image.paste(logo, (LOGO_PASTE_X, LOGO_PASTE_Y))
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise ShipmentPreparationError(
                f"Label preparation failed: {error}", shipment=shipment
            ) from error

        return PreparedLabel(shipment=shipment, image=image)
