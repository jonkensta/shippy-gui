"""Worker thread for creating and printing shipping labels."""

import os
from typing import Optional

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
from PIL import Image
from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import LOGO_PASTE_X, LOGO_PASTE_Y, OUNCES_PER_POUND
from shippy_gui.core.misc import grab_png_from_url
from shippy_gui.core.services import ShipmentService
from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.printing.printer_manager import print_image


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
        self.service = shipment_service
        self.from_address = from_address
        self.to_address = to_address
        self.weight_lbs = weight_lbs
        self.printer_name = printer_name
        self.logo_path = logo_path
        self.use_dialog = use_dialog
        self.shipment = None

    def run(self):
        """Execute the shipment workflow."""
        try:
            # Step 1: Build and verify return address
            self.progress.emit("Building return address...")
            from_addr = self.service.create_address(self.from_address)

            try:
                self.progress.emit("Verifying return address...")
                self.service.verify_address(from_addr.id)
            except easypost.errors.InvalidRequestError:
                self.warning.emit(
                    "Failed to verify return address. Please check your config.ini."
                )

            # Step 2: Build and verify recipient address
            self.progress.emit("Building recipient address...")
            to_addr = self.service.create_address(self.to_address)

            try:
                self.progress.emit("Verifying recipient address...")
                self.service.verify_address(to_addr.id)
            except easypost.errors.InvalidRequestError:
                self.warning.emit(
                    "Failed to verify recipient address. Please double-check before shipping."
                )

            # Step 3: Purchase postage
            self.progress.emit("Purchasing postage...")
            weight_oz = self.weight_lbs * OUNCES_PER_POUND
            self.shipment = self.service.buy_shipment(
                from_addr.id, to_addr.id, weight_oz
            )

            # Step 4: Download label
            self.progress.emit("Downloading label...")
            label_url = self.shipment.postage_label.label_url
            image = self._download_png(label_url)

            # Step 5: Add logo if provided
            if self.logo_path and os.path.exists(self.logo_path):
                self.progress.emit("Adding logo...")
                logo = Image.open(self.logo_path)
                image.paste(logo, (LOGO_PASTE_X, LOGO_PASTE_Y))

            # Step 6: Print (or emit for dialog)
            if self.use_dialog:
                # Contract: Only emitted when use_dialog is True
                self.label_ready.emit(image, self.printer_name, self.shipment)
                # Do not emit success here; UI thread handles the rest
                return

            # Quick print path (background)
            self.progress.emit("Printing label...")
            print_image(image, self.printer_name)

            # Success!
            self.success.emit(
                f"Label printed successfully! Tracking: {self.shipment.tracking_code}"
            )

        except easypost.errors.APIError as e:
            self._handle_error(f"EasyPost API error: {e}")
        except RuntimeError as e:
            # Printing errors
            self._handle_error(f"Printing error: {e}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._handle_error(f"Unexpected error: {e}")

    def _handle_error(self, error_message: str) -> None:
        """Handle an error during shipment workflow, attempting refund if needed.

        Args:
            error_message: The error message to include in the signal.
        """
        if self.shipment:
            try:
                self.progress.emit("Requesting refund...")
                self.service.refund_shipment(self.shipment.id)
                self.error.emit(f"{error_message}. Refund requested.")
            except easypost.errors.APIError as refund_error:
                self.error.emit(f"{error_message}. Refund also failed: {refund_error}")
            except Exception as refund_error:  # pylint: disable=broad-exception-caught
                self.error.emit(f"{error_message}. Refund also failed: {refund_error}")
        else:
            self.error.emit(f"Shipment creation failed: {error_message}")

    def _download_png(self, url: str) -> Image.Image:
        """Download a PNG image from a URL.

        Args:
            url: URL of the PNG image

        Returns:
            PIL Image object
        """
        return grab_png_from_url(url)
