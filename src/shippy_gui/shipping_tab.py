"Unified shipping tab with manual address entry."

# pylint: disable=duplicate-code  # Intentional patterns shared with settings_dialog

from pathlib import Path
from typing import Optional, Any

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error
import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QLabel,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.printing.printer_manager import (
    get_available_printers,
    get_default_printer,
    print_image_with_dialog,
)
from shippy_gui.core.config_manager import ConfigManager
from shippy_gui.core.constants import STATUS_COLORS, WEIGHT_MAX_LBS, WEIGHT_MIN_LBS
from shippy_gui.core.addresses import AddressParser
from shippy_gui.widgets.autocomplete import setup_google_maps_autocomplete
from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShippingTab(
    QWidget
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Tab for unified shipping with address lookup."""

    REQUIRED_ADDRESS_FIELDS = ["street1", "city", "state", "zipcode"]
    RECIPIENT_INPUT_FIELDS = [
        "name_input",
        "company_input",
        "street1_input",
        "street2_input",
        "city_input",
        "state_input",
        "zipcode_input",
    ]

    def __init__(self, config_path: Optional[str] = None, parent=None):
        """Initialize the shipping tab.

        Args:
            config_path: Path to config.ini file
            parent: Parent widget
        """
        super().__init__(parent)
        self._config_manager = ConfigManager(config_path)

        self.gmaps = None
        self.address_parser = None
        self.easypost_client = None
        self.logo_path = None
        self.shipment_worker = None
        self._init_api_clients()
        self._load_logo()
        self._init_ui()
        self._load_printers()
        self._setup_autocomplete()

    @property
    def config(self):
        """Get the loaded configuration."""
        return self._config_manager.config

    @property
    def config_path(self) -> str:
        """Get the config file path."""
        return self._config_manager.config_path

    def _init_api_clients(self):
        """Load configuration and initialize API clients."""
        if not self._config_manager.load(parent_widget=self):
            return

        config = self._config_manager.config
        if config is None:
            return

        # Initialize Google Maps client
        self.gmaps = googlemaps.Client(key=config.googlemaps.apikey)
        self.address_parser = AddressParser(self.gmaps)

        # Initialize EasyPost client
        self.easypost_client = easypost.EasyPostClient(config.easypost.apikey)

    def _load_logo(self):
        """Load logo image if available."""
        # Look for logo in assets directory
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        if logo_path.exists():
            self.logo_path = str(logo_path)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()
        layout.addWidget(self._build_lookup_group())
        layout.addWidget(self._build_address_group())
        layout.addLayout(self._build_shipment_form())
        layout.addWidget(self._build_create_button())
        layout.addWidget(self._build_status_label())

        layout.addStretch()
        self.setLayout(layout)

    def _build_lookup_group(self) -> QGroupBox:
        """Build the quick lookup section."""
        lookup_group = QGroupBox("Quick Lookup")
        lookup_layout = QVBoxLayout()

        address_search_layout = QHBoxLayout()
        address_search_layout.addWidget(QLabel("Address Search:"))
        self.address_search_input = QLineEdit()
        self.address_search_input.setPlaceholderText("Start typing address...")
        self.address_search_input.setToolTip(
            "Type any US address and select a suggestion to populate the fields below."
        )
        address_search_layout.addWidget(self.address_search_input, 1)
        lookup_layout.addLayout(address_search_layout)

        lookup_group.setLayout(lookup_layout)
        return lookup_group

    def _build_address_group(self) -> QGroupBox:
        """Build the recipient address section."""
        address_group = QGroupBox("Recipient Address")
        address_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Recipient name")
        self.name_input.setToolTip("Recipient's full name")
        address_form.addRow("Name:", self.name_input)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Optional")
        self.company_input.setToolTip("Company or institution name (optional)")
        address_form.addRow("Company:", self.company_input)

        self.street1_input = QLineEdit()
        self.street1_input.setToolTip("Street address line 1 (required)")
        address_form.addRow("Street 1:", self.street1_input)

        self.street2_input = QLineEdit()
        self.street2_input.setPlaceholderText("Optional")
        self.street2_input.setToolTip("Apartment, suite, unit, etc. (optional)")
        address_form.addRow("Street 2:", self.street2_input)

        self.city_input = QLineEdit()
        self.city_input.setToolTip("City name (required)")
        address_form.addRow("City:", self.city_input)

        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("TX")
        self.state_input.setMaxLength(2)
        self.state_input.setToolTip("Two-letter state code (e.g., TX, CA, NY)")
        address_form.addRow("State:", self.state_input)

        self.zipcode_input = QLineEdit()
        self.zipcode_input.setPlaceholderText("78703")
        self.zipcode_input.setToolTip("5-digit ZIP code (required)")
        address_form.addRow("ZIP Code:", self.zipcode_input)

        address_group.setLayout(address_form)
        return address_group

    def _build_shipment_form(self) -> QFormLayout:
        """Build shipment detail inputs."""
        shipment_form = QFormLayout()

        self.weight_input = QSpinBox()
        self.weight_input.setRange(WEIGHT_MIN_LBS, WEIGHT_MAX_LBS)
        self.weight_input.setValue(WEIGHT_MIN_LBS)
        self.weight_input.setSuffix(" lbs")
        self.weight_input.setToolTip(
            "Package weight in pounds (1-70 lbs for Library Mail rate)"
        )
        shipment_form.addRow("Weight:", self.weight_input)

        self.printer_combo = QComboBox()
        self.printer_combo.setToolTip(
            "Select printer for shipping label (4x6 label size)"
        )
        shipment_form.addRow("Printer:", self.printer_combo)

        return shipment_form

    def _build_create_button(self) -> QPushButton:
        """Build the create label button."""
        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.setToolTip(
            "Purchase postage, download label, and print to selected printer.\n"
            "Hold Shift + Click to choose printer via system dialog.\n"
            "Label will be automatically refunded if printing fails."
        )
        self.create_button.clicked.connect(self._create_label)
        return self.create_button

    def _build_status_label(self) -> QLabel:
        """Build the status label."""
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return self.status_label

    def _load_printers(self):
        """Load available printers into the combo box."""
        printers = get_available_printers()

        if not printers:
            self.printer_combo.addItem("No printers found")
            self.create_button.setEnabled(False)
            return

        self.printer_combo.addItems(printers)

        # Select default printer if available
        default_printer = get_default_printer()
        if default_printer and default_printer in printers:
            index = printers.index(default_printer)
            self.printer_combo.setCurrentIndex(index)

    def _setup_autocomplete(self):
        """Set up Google Maps autocomplete on address search field."""
        if not self.gmaps:
            return

        # Set up autocomplete with 500ms debounce (balance between responsiveness and API usage)
        completer = setup_google_maps_autocomplete(
            self.address_search_input, self.gmaps, debounce_delay=500
        )

        # Automatically load address when selected from suggestions
        completer.activated.connect(self._load_address)

    def _clear_recipient_fields(self):
        """Clear all recipient address fields."""
        for field_name in self.RECIPIENT_INPUT_FIELDS:
            getattr(self, field_name).clear()

    def _validate_required_fields(self) -> Optional[str]:
        """Validate required fields and return an error message if invalid."""
        required_fields = [
            ("Please enter recipient name", self.name_input),
            ("Please enter street address", self.street1_input),
            ("Please enter city", self.city_input),
            ("Please enter state", self.state_input),
            ("Please enter ZIP code", self.zipcode_input),
        ]

        for message, field in required_fields:
            if not field.text().strip():
                return message

        if self.printer_combo.currentText() == "No printers found":
            return "No printer selected"

        return None

    def _load_address(self, selected_address: Optional[str] = None):
        """Parse selected address and populate address fields.

        Args:
            selected_address: Optional address string from autocomplete.
                            If not provided, uses the current text in search input.
        """
        search_query = selected_address or self.address_search_input.text().strip()
        if not search_query:
            self._set_status("Please enter an address to search", "error")
            return

        if not self.address_parser:
            QMessageBox.critical(
                self,
                "Configuration Error",
                "Google Maps not configured. Please check your config.ini file.",
            )
            return

        self._set_status(f"Parsing address: {search_query}...", "info")

        try:
            # Parse the address using Google Geocoding API
            address_parts = self.address_parser(search_query)

            if not address_parts:
                self._set_status("Could not parse address", "error")
                QMessageBox.warning(
                    self,
                    "Address Parse Error",
                    f"Could not parse the selected address:\n\n{search_query}\n\n"
                    "Please try a different address or enter manually.",
                )
                return

            self._populate_address_fields(address_parts)

            # Clear search input after successful load
            # Use singleShot to ensure it clears after QCompleter has finished updating the text
            QTimer.singleShot(0, self.address_search_input.clear)

            # Check if address verification failed
            missing_fields = self._missing_required_address_fields(address_parts)

            if missing_fields:
                self._set_status(
                    f"Address incomplete - missing: {', '.join(missing_fields)}",
                    "warning",
                )
            else:
                self._set_status("Address loaded successfully", "success")

        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ) as e:
            self._set_status("Address search failed", "error")
            QMessageBox.critical(
                self,
                "Address Search Error",
                f"Google Maps API error:\n\n{e}",
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._set_status("Address search failed", "error")
            QMessageBox.critical(
                self,
                "Address Search Error",
                f"Error parsing address:\n\n{e}",
            )

    def _populate_address_fields(self, address_parts: dict) -> None:
        """Populate address fields from parsed components."""
        self._clear_recipient_fields()

        field_widgets = {
            "street1": self.street1_input,
            "street2": self.street2_input,
            "city": self.city_input,
            "state": self.state_input,
            "zipcode": self.zipcode_input,
        }

        for key, widget in field_widgets.items():
            if key in address_parts:
                widget.setText(address_parts.get(key, "") or "")

    def _missing_required_address_fields(self, address_parts: dict) -> list[str]:
        """Return required address fields that are missing."""
        return [
            field
            for field in self.REQUIRED_ADDRESS_FIELDS
            if field not in address_parts
        ]

    def _create_label(self):  # pylint: disable=too-many-return-statements
        """Create and print shipping label."""
        # Validate required fields
        validation_error = self._validate_required_fields()
        if validation_error:
            self._set_status(validation_error, "error")
            return

        # Check for required services
        if not self.easypost_client:
            QMessageBox.critical(
                self,
                "Configuration Error",
                "EasyPost API not configured. Please check your config.ini file.",
            )
            return

        if not self.config:
            QMessageBox.critical(
                self,
                "Configuration Error",
                "Configuration not loaded. Please check your config.ini file.",
            )
            return

        # Disable create button during shipment
        self.create_button.setEnabled(False)

        # Build address dictionaries
        from_address_dict = {
            "name": self.config.return_address.name,
            "street1": self.config.return_address.street1,
            "street2": self.config.return_address.street2,
            "city": self.config.return_address.city,
            "state": self.config.return_address.state,
            "zipcode": self.config.return_address.zipcode,
        }

        to_address_dict = {
            "name": self.name_input.text().strip(),
            "company": self.company_input.text().strip() or "",
            "street1": self.street1_input.text().strip(),
            "street2": self.street2_input.text().strip() or "",
            "city": self.city_input.text().strip(),
            "state": self.state_input.text().strip(),
            "zipcode": self.zipcode_input.text().strip(),
        }

        # Get weight and printer
        weight_lbs = self.weight_input.value()
        printer_name = self.printer_combo.currentText()

        # Check for Shift key to enable print dialog
        use_dialog = (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ) == Qt.KeyboardModifier.ShiftModifier

        # Create and start worker thread
        self.shipment_worker = ShipmentWorker(
            easypost_client=self.easypost_client,
            from_address_dict=from_address_dict,
            to_address_dict=to_address_dict,
            weight_lbs=weight_lbs,
            printer_name=printer_name,
            logo_path=self.logo_path,
            use_dialog=use_dialog,
        )

        # Connect signals
        self.shipment_worker.progress.connect(lambda msg: self._set_status(msg, "info"))
        self.shipment_worker.warning.connect(
            lambda msg: self._set_status(msg, "warning")
        )
        self.shipment_worker.success.connect(self._on_shipment_success)
        self.shipment_worker.error.connect(self._on_shipment_error)
        self.shipment_worker.finished.connect(self._on_shipment_finished)
        self.shipment_worker.label_ready.connect(self._on_label_ready)

        # Start the worker
        self.shipment_worker.start()

    def _on_label_ready(self, image, printer_name: str, shipment: Any):
        """Handle label ready for printing via system dialog.

        Args:
            image: PIL Image object
            printer_name: Name of printer to pre-select
            shipment: EasyPost Shipment object for refunding
        """
        # Note: The worker thread finishes immediately after emitting this signal,
        # which triggers _on_shipment_finished and re-enables the Create button.
        # This is safe because the QPrintDialog is modal and blocks UI interaction.

        if not self.easypost_client:
            return

        result = print_image_with_dialog(
            image, self, preferred_printer_name=printer_name
        )

        if result == "printed":
            # Success! Reuse existing success handler
            self._on_shipment_success(
                f"Label printed successfully! Tracking: {shipment.tracking_code}"
            )

        elif result == "canceled":
            self._refund_shipment(shipment, "Print canceled")

        elif result == "failed":
            self._refund_shipment(shipment, "Print failed")

    def _refund_shipment(self, shipment, reason: str) -> None:
        """Request a refund for a shipment.

        Args:
            shipment: EasyPost Shipment object.
            reason: Reason for the refund (e.g., "Print canceled", "Print failed").
        """
        if not self.easypost_client:
            self._set_status("Cannot refund: EasyPost not configured", "error")
            return

        self._set_status("Requesting refund...", "warning")
        try:
            self.easypost_client.shipment.refund(shipment.id)
            self._set_status(f"{reason}. Shipment refunded.", "warning")
            QMessageBox.warning(
                self,
                reason,
                f"{reason}. The shipment has been refunded.",
            )
        except easypost.errors.APIError as e:
            self._set_status("Refund failed", "error")
            QMessageBox.critical(
                self,
                "Refund Error",
                f"{reason} but refund failed.\nEasyPost error: {e}",
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._set_status("Refund failed", "error")
            QMessageBox.critical(
                self,
                "Refund Error",
                f"{reason} but refund failed.\nError: {e}",
            )

    def _on_shipment_success(self, message: str):
        """Handle successful shipment.

        Args:
            message: Success message with tracking info
        """
        self._set_status(message, "success")

        # Clear all input fields for next shipment
        self.address_search_input.clear()
        self._clear_recipient_fields()
        self.weight_input.setValue(WEIGHT_MIN_LBS)

        # Focus on first input
        self.address_search_input.setFocus()

    def _on_shipment_error(self, message: str):
        """Handle shipment error.

        Args:
            message: Error message
        """
        self._set_status("Shipment failed", "error")
        QMessageBox.critical(
            self,
            "Shipment Error",
            message,
        )

    def _on_shipment_finished(self):
        """Handle worker thread completion."""
        # Re-enable create button
        self.create_button.setEnabled(True)
        self.shipment_worker = None

    def _set_status(self, message: str, status_type: str = "info"):
        """Set status message with color coding.

        Args:
            message: Status message to display
            status_type: One of "info", "success", "warning", "error"
        """
        color = STATUS_COLORS.get(status_type, STATUS_COLORS["info"])
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
