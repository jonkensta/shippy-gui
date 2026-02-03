"""Worker thread for creating and printing shipping labels."""

import os
from typing import Optional

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
from PIL import Image
from PySide6.QtCore import QThread, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.misc import grab_png_from_url
from shippy_gui.core.shipping import build_address, build_shipment
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
        easypost_client: easypost.EasyPostClient,
        from_address_dict: dict,
        to_address_dict: dict,
        weight_lbs: int,
        printer_name: str,
        logo_path: Optional[str] = None,
        use_dialog: bool = False,
    ):
        """Initialize the shipment worker.

        Args:
            easypost_client: EasyPost API client
            from_address_dict: Return address dictionary
            to_address_dict: Recipient address dictionary
            weight_lbs: Package weight in pounds
            printer_name: Name of printer to use
            logo_path: Optional path to logo image to overlay
            use_dialog: Whether to use system print dialog (default: False)
        """
        super().__init__()
        self.easypost_client = easypost_client
        self.from_address_dict = from_address_dict
        self.to_address_dict = to_address_dict
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
            from_addr = build_address(self.easypost_client, **self.from_address_dict)

            try:
                self.progress.emit("Verifying return address...")
                self.easypost_client.address.verify(from_addr.id)
            except easypost.errors.InvalidRequestError:
                self.warning.emit(
                    "Failed to verify return address. Please check your config.ini."
                )

            # Step 2: Build and verify recipient address
            self.progress.emit("Building recipient address...")
            to_addr = build_address(self.easypost_client, **self.to_address_dict)

            try:
                self.progress.emit("Verifying recipient address...")
                self.easypost_client.address.verify(to_addr.id)
            except easypost.errors.InvalidRequestError:
                self.warning.emit(
                    "Failed to verify recipient address. Please double-check before shipping."
                )

            # Step 3: Purchase postage
            self.progress.emit("Purchasing postage...")
            weight_oz = self.weight_lbs * 16  # Convert to ounces
            self.shipment = build_shipment(
                self.easypost_client, from_addr, to_addr, weight_oz
            )

            # Step 4: Download label
            self.progress.emit("Downloading label...")
            label_url = self.shipment.postage_label.label_url
            image = self._download_png(label_url)

            # Step 5: Add logo if provided
            if self.logo_path and os.path.exists(self.logo_path):
                self.progress.emit("Adding logo...")
                logo = Image.open(self.logo_path)
                image.paste(logo, (450, 425))

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

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Refund the shipment if we created one
            if self.shipment:
                try:
                    self.progress.emit("Requesting refund...")
                    self.easypost_client.shipment.refund(self.shipment.id)
                    self.error.emit(
                        f"Printing failed. Refund requested. Error: {str(e)}"
                    )
                # pylint: disable-next=broad-exception-caught
                except Exception as refund_error:
                    self.error.emit(
                        f"Printing failed and refund failed. Error: {str(e)}. "
                        f"Refund error: {str(refund_error)}"
                    )
            else:
                self.error.emit(f"Shipment creation failed: {str(e)}")

    def _download_png(self, url: str) -> Image.Image:
        """Download a PNG image from a URL.

        Args:
            url: URL of the PNG image

        Returns:
            PIL Image object
        """
        return grab_png_from_url(url)
