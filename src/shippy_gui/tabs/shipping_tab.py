"""Unified shipping tab with inmate lookup and manual address entry."""

import configparser
import os
from pathlib import Path

import easypost
import googlemaps
from PIL import Image
from PySide6.QtWidgets import (
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
    QCompleter,
)
from PySide6.QtCore import Qt

from shippy_gui.printing.printer_manager import (
    get_available_printers,
    get_default_printer,
)
from shippy_gui.core.server import Server
from shippy_gui.core.models import Config
from shippy_gui.core.addresses import AddressParser
from shippy_gui.widgets.selection_dialog import SelectionDialog
from shippy_gui.widgets.autocomplete import setup_google_maps_autocomplete
from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShippingTab(QWidget):
    """Tab for unified shipping with optional inmate/address lookup."""

    def __init__(self, config_path: str = None, parent=None):
        """Initialize the shipping tab.

        Args:
            config_path: Path to config.ini file
            parent: Parent widget
        """
        super().__init__(parent)
        self.config_path = config_path or os.path.join(os.getcwd(), "config.ini")
        self.server = None
        self.gmaps = None
        self.address_parser = None
        self.easypost_client = None
        self.config = None
        self.logo_path = None
        self.units_map = {}  # Map of unit name (uppercase) -> composite ID
        self.shipment_worker = None
        self._load_config()
        self._load_logo()
        self._init_ui()
        self._load_printers()
        self._setup_autocomplete()
        self._load_units()

    def _load_config(self):
        """Load configuration and initialize server."""
        try:
            config_parser = configparser.ConfigParser()
            config_parser.read(self.config_path)
            config_dict = {
                section: dict(config_parser[section])
                for section in config_parser.sections()
            }
            self.config = Config.model_validate(config_dict)
            self.server = Server.from_config(self.config.ibp)

            # Initialize Google Maps client
            self.gmaps = googlemaps.Client(key=self.config.googlemaps.apikey)
            self.address_parser = AddressParser(self.gmaps)

            # Initialize EasyPost client
            self.easypost_client = easypost.EasyPostClient(self.config.easypost.apikey)
        except Exception as e:
            # Server/gmaps/easypost will be None if config fails to load
            print(f"Failed to load config: {e}")

    def _load_logo(self):
        """Load logo image if available."""
        # Look for logo in assets directory
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        if logo_path.exists():
            self.logo_path = str(logo_path)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Quick Lookup Section
        lookup_group = QGroupBox("Quick Lookup (optional)")
        lookup_layout = QVBoxLayout()

        # Inmate Lookup
        inmate_layout = QHBoxLayout()
        inmate_layout.addWidget(QLabel("Inmate Lookup:"))
        self.inmate_input = QLineEdit()
        self.inmate_input.setPlaceholderText("Barcode, ID, or Request ID")
        self.inmate_input.setToolTip(
            "Enter inmate barcode (TEX-12345678-0), inmate ID (12345678), or request ID.\n"
            "Searches both Texas and Federal jurisdictions."
        )
        inmate_layout.addWidget(self.inmate_input, 1)
        self.inmate_lookup_button = QPushButton("Lookup")
        self.inmate_lookup_button.setToolTip(
            "Search for inmate and load their name and unit address"
        )
        self.inmate_lookup_button.clicked.connect(self._lookup_inmate)
        inmate_layout.addWidget(self.inmate_lookup_button)
        lookup_layout.addLayout(inmate_layout)

        # OR separator
        or_label = QLabel("- OR -")
        or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label.setStyleSheet("color: #666; font-style: italic;")
        lookup_layout.addWidget(or_label)

        # Address Search
        address_search_layout = QHBoxLayout()
        address_search_layout.addWidget(QLabel("Address Search:"))
        self.address_search_input = QLineEdit()
        self.address_search_input.setPlaceholderText("Start typing address...")
        self.address_search_input.setToolTip(
            "Type any US address and select from autocomplete suggestions.\n"
            "Click 'Load' to parse and populate the address fields below."
        )
        address_search_layout.addWidget(self.address_search_input, 1)
        self.address_search_button = QPushButton("Load")
        self.address_search_button.setToolTip(
            "Parse selected address and load into fields below"
        )
        self.address_search_button.clicked.connect(self._load_address)
        address_search_layout.addWidget(self.address_search_button)
        lookup_layout.addLayout(address_search_layout)

        # OR separator
        or_label2 = QLabel("- OR -")
        or_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        or_label2.setStyleSheet("color: #666; font-style: italic;")
        lookup_layout.addWidget(or_label2)

        # Unit Lookup
        unit_lookup_layout = QHBoxLayout()
        unit_lookup_layout.addWidget(QLabel("Unit Lookup:"))
        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("Start typing unit name...")
        self.unit_input.setToolTip(
            "Type a Texas prison unit name and select from autocomplete.\n"
            "Click 'Load' to address the package to the unit mailroom."
        )
        unit_lookup_layout.addWidget(self.unit_input, 1)
        self.unit_lookup_button = QPushButton("Load")
        self.unit_lookup_button.setToolTip(
            "Load unit address with 'ATTN: Mailroom Staff' as recipient"
        )
        self.unit_lookup_button.clicked.connect(self._load_unit)
        unit_lookup_layout.addWidget(self.unit_lookup_button)
        lookup_layout.addLayout(unit_lookup_layout)

        lookup_group.setLayout(lookup_layout)
        layout.addWidget(lookup_group)

        # Recipient Address Section
        address_group = QGroupBox("Recipient Address")
        address_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Recipient name")
        self.name_input.setToolTip(
            "Recipient's full name or 'ATTN: Mailroom Staff' for unit shipments"
        )
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
        layout.addWidget(address_group)

        # Shipment Details Section
        shipment_form = QFormLayout()

        self.weight_input = QSpinBox()
        self.weight_input.setRange(1, 70)
        self.weight_input.setValue(1)
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

        layout.addLayout(shipment_form)

        # Create Label Button
        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.setToolTip(
            "Purchase postage, download label, and print to selected printer.\n"
            "Label will be automatically refunded if printing fails."
        )
        self.create_button.clicked.connect(self._create_label)
        layout.addWidget(self.create_button)

        # Status Label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

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

    def _lookup_inmate(self):
        """Look up inmate and populate address fields."""
        inmate_id = self.inmate_input.text().strip()
        if not inmate_id:
            self._set_status("Please enter a barcode, ID, or request ID", "error")
            return

        if not self.server:
            QMessageBox.critical(
                self,
                "Configuration Error",
                "Server not configured. Please check your config.ini file.",
            )
            return

        self._set_status(f"Looking up inmate: {inmate_id}...", "info")

        try:
            result, strategy = self.server.find_inmate(inmate_id)

            # Handle multiple matches
            if strategy == "multiple_matches":
                # result is a list of (jurisdiction, inmate_data) tuples
                options = []
                for jurisdiction, inmate in result:
                    unit_name = (
                        inmate.get("unit", {}).get("name", "Unknown Unit")
                        if inmate.get("unit")
                        else "No Unit"
                    )
                    first_name = inmate.get("first_name", "")
                    last_name = inmate.get("last_name", "")
                    name = f"{first_name} {last_name}".strip() or "Unknown"
                    inmate_id_str = inmate.get("id", "")
                    display = f"{jurisdiction} - {name} ({inmate_id_str}) - {unit_name}"
                    options.append((display, (jurisdiction, inmate)))

                dialog = SelectionDialog(
                    "Multiple Inmates Found",
                    "Please select the correct inmate:",
                    options,
                    self,
                )

                if dialog.exec():
                    selected = dialog.get_selected()
                    if selected:
                        jurisdiction, inmate = selected
                        self._populate_from_inmate(inmate)
                        self._set_status(
                            f"Loaded inmate from {jurisdiction}", "success"
                        )
                else:
                    self._set_status("Lookup cancelled", "warning")
            else:
                # Single match - result is the inmate dict
                self._populate_from_inmate(result)
                self._set_status(f"Found inmate using {strategy}", "success")

        except ValueError as e:
            self._set_status(str(e), "error")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Lookup Error",
                f"Error looking up inmate:\n\n{str(e)}",
            )
            self._set_status("Lookup failed", "error")

    def _populate_from_inmate(self, inmate: dict):
        """Populate address fields from inmate data.

        Args:
            inmate: Inmate dict from server
        """
        # Clear all fields first
        self._clear_recipient_fields()

        # Populate name from inmate
        first_name = inmate.get("first_name", "")
        last_name = inmate.get("last_name", "")
        name = f"{first_name} {last_name}".strip()
        if name:
            self.name_input.setText(name)
        else:
            self.name_input.setText(f"Inmate #{inmate.get('id', '')}")

        # Populate address from unit
        unit = inmate.get("unit")
        if unit:
            self.street1_input.setText(unit.get("street1", ""))
            self.street2_input.setText(unit.get("street2", "") or "")
            self.city_input.setText(unit.get("city", ""))
            self.state_input.setText(unit.get("state", ""))
            self.zipcode_input.setText(unit.get("zipcode", ""))

    def _setup_autocomplete(self):
        """Set up Google Maps autocomplete on address search field."""
        if not self.gmaps:
            return

        # Set up autocomplete with 500ms debounce (balance between responsiveness and API usage)
        setup_google_maps_autocomplete(
            self.address_search_input, self.gmaps, debounce_delay=500
        )

        # Note: Don't connect activated signal - only load when button is clicked

    def _load_units(self):
        """Load units list from server and set up autocomplete."""
        if not self.server:
            return

        try:
            # Fetch units (already filtered to Texas only)
            self.units_map = self.server.unit_ids()

            if not self.units_map:
                return

            # Set up autocomplete with unit names
            unit_names = sorted(self.units_map.keys())
            completer = QCompleter(unit_names, self.unit_input)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            self.unit_input.setCompleter(completer)

        except Exception as e:
            print(f"Failed to load units: {e}")

    def _clear_recipient_fields(self):
        """Clear all recipient address fields."""
        self.name_input.clear()
        self.company_input.clear()
        self.street1_input.clear()
        self.street2_input.clear()
        self.city_input.clear()
        self.state_input.clear()
        self.zipcode_input.clear()

    def _load_address(self):
        """Parse selected address and populate address fields."""
        search_query = self.address_search_input.text().strip()
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
                    f"Could not parse the selected address:\n\n{search_query}\n\nPlease try a different address or enter manually.",
                )
                return

            # Clear all fields first
            self._clear_recipient_fields()

            # Populate address fields from parsed components
            if "street1" in address_parts:
                self.street1_input.setText(address_parts["street1"])

            if "street2" in address_parts:
                self.street2_input.setText(address_parts.get("street2", ""))

            if "city" in address_parts:
                self.city_input.setText(address_parts["city"])

            if "state" in address_parts:
                self.state_input.setText(address_parts["state"])

            if "zipcode" in address_parts:
                self.zipcode_input.setText(address_parts["zipcode"])

            # Check if address verification failed
            required_fields = ["street1", "city", "state", "zipcode"]
            missing_fields = [
                field for field in required_fields if field not in address_parts
            ]

            if missing_fields:
                self._set_status(
                    f"Address incomplete - missing: {', '.join(missing_fields)}",
                    "warning",
                )
            else:
                self._set_status("Address loaded successfully", "success")

        except Exception as e:
            self._set_status("Address search failed", "error")
            QMessageBox.critical(
                self,
                "Address Search Error",
                f"Error parsing address:\n\n{str(e)}",
            )

    def _load_unit(self):
        """Load unit address and populate address fields."""
        unit_name = self.unit_input.text().strip().upper()
        if not unit_name:
            self._set_status("Please enter a unit name", "error")
            return

        # Check if unit exists in our map
        if unit_name not in self.units_map:
            self._set_status("Invalid unit name", "error")
            QMessageBox.warning(
                self,
                "Invalid Unit",
                f"'{unit_name}' is not a recognized unit.\n\nPlease select from the autocomplete suggestions.",
            )
            return

        if not self.server:
            QMessageBox.critical(
                self,
                "Configuration Error",
                "Server not configured. Please check your config.ini file.",
            )
            return

        # Get unit composite ID and fetch address
        composite_id = self.units_map[unit_name]
        self._set_status(f"Fetching address for {unit_name}...", "info")

        try:
            address_dict = self.server.unit_address(composite_id)

            # Clear all fields first
            self._clear_recipient_fields()

            # Populate name field with "ATTN: Mailroom Staff"
            self.name_input.setText(address_dict["name"])

            # Populate address fields
            self.street1_input.setText(address_dict["street1"])
            self.street2_input.setText(address_dict.get("street2", ""))
            self.city_input.setText(address_dict["city"])
            self.state_input.setText(address_dict["state"])
            self.zipcode_input.setText(address_dict["zipcode"])

            self._set_status(f"Loaded address for {unit_name}", "success")

        except Exception as e:
            self._set_status("Failed to fetch unit address", "error")
            QMessageBox.critical(
                self,
                "Unit Address Error",
                f"Error fetching address for {unit_name}:\n\n{str(e)}",
            )

    def _create_label(self):
        """Create and print shipping label."""
        # Validate required fields
        if not self.name_input.text().strip():
            self._set_status("Please enter recipient name", "error")
            return

        if not self.street1_input.text().strip():
            self._set_status("Please enter street address", "error")
            return

        if not self.city_input.text().strip():
            self._set_status("Please enter city", "error")
            return

        if not self.state_input.text().strip():
            self._set_status("Please enter state", "error")
            return

        if not self.zipcode_input.text().strip():
            self._set_status("Please enter ZIP code", "error")
            return

        if self.printer_combo.currentText() == "No printers found":
            self._set_status("No printer selected", "error")
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

        # Create and start worker thread
        self.shipment_worker = ShipmentWorker(
            easypost_client=self.easypost_client,
            from_address_dict=from_address_dict,
            to_address_dict=to_address_dict,
            weight_lbs=weight_lbs,
            printer_name=printer_name,
            logo_path=self.logo_path,
        )

        # Connect signals
        self.shipment_worker.progress.connect(lambda msg: self._set_status(msg, "info"))
        self.shipment_worker.warning.connect(
            lambda msg: self._set_status(msg, "warning")
        )
        self.shipment_worker.success.connect(self._on_shipment_success)
        self.shipment_worker.error.connect(self._on_shipment_error)
        self.shipment_worker.finished.connect(self._on_shipment_finished)

        # Start the worker
        self.shipment_worker.start()

    def _on_shipment_success(self, message: str):
        """Handle successful shipment.

        Args:
            message: Success message with tracking info
        """
        self._set_status(message, "success")

        # Clear all input fields for next shipment
        self.inmate_input.clear()
        self.address_search_input.clear()
        self.unit_input.clear()
        self.name_input.clear()
        self.company_input.clear()
        self.street1_input.clear()
        self.street2_input.clear()
        self.city_input.clear()
        self.state_input.clear()
        self.zipcode_input.clear()
        self.weight_input.setValue(1)

        # Focus on first input
        self.inmate_input.setFocus()

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
        colors = {
            "info": "#0066CC",  # Blue
            "success": "#008800",  # Green
            "warning": "#FF8800",  # Yellow/Orange
            "error": "#CC0000",  # Red
        }
        color = colors.get(status_type, colors["info"])
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
