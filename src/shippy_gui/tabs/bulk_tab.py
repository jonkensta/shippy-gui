"""Bulk shipping mode tab."""

import configparser
import os
from pathlib import Path

import easypost
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QLabel,
    QMessageBox,
    QCompleter,
)
from PySide6.QtCore import Qt

from shippy_gui.printing.printer_manager import get_available_printers, get_default_printer
from shippy_gui.core.server import Server
from shippy_gui.core.models import Config
from shippy_gui.workers.shipment_worker import ShipmentWorker


class BulkTab(QWidget):
    """Tab for bulk unit shipping."""

    def __init__(self, config_path: str = None, parent=None):
        """Initialize the bulk shipping tab.

        Args:
            config_path: Path to config.ini file
            parent: Parent widget
        """
        super().__init__(parent)
        self.config_path = config_path or os.path.join(os.getcwd(), "config.ini")
        self.server = None
        self.easypost_client = None
        self.config = None
        self.logo_path = None
        self.units_map = {}  # Map of unit name (uppercase) -> composite ID
        self.shipment_worker = None
        self._load_config()
        self._load_logo()
        self._init_ui()
        self._load_printers()
        self._load_units()

    def _load_config(self):
        """Load configuration and initialize server."""
        try:
            config_parser = configparser.ConfigParser()
            config_parser.read(self.config_path)
            config_dict = {section: dict(config_parser[section]) for section in config_parser.sections()}
            self.config = Config.model_validate(config_dict)
            self.server = Server.from_config(self.config.ibp)

            # Initialize EasyPost client
            self.easypost_client = easypost.EasyPostClient(self.config.easypost.apikey)
        except Exception as e:
            # Server/easypost will be None if config fails to load
            print(f"Failed to load config: {e}")

    def _load_logo(self):
        """Load logo image if available."""
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        if logo_path.exists():
            self.logo_path = str(logo_path)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Form layout for inputs
        form_layout = QFormLayout()

        # Unit name input with autocomplete
        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("Start typing unit name...")
        form_layout.addRow("Prison Unit:", self.unit_input)

        # Weight input
        self.weight_input = QSpinBox()
        self.weight_input.setRange(1, 70)
        self.weight_input.setValue(1)
        self.weight_input.setSuffix(" lbs")
        form_layout.addRow("Weight:", self.weight_input)

        # Printer selection
        self.printer_combo = QComboBox()
        form_layout.addRow("Printer:", self.printer_combo)

        layout.addLayout(form_layout)

        # Create Label Button
        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
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

    def _load_units(self):
        """Load units list from server and set up autocomplete."""
        if not self.server:
            self._set_status("Server not configured", "error")
            self.create_button.setEnabled(False)
            return

        self._set_status("Loading units list from server...", "info")

        try:
            # Fetch units (already filtered to Texas only)
            self.units_map = self.server.unit_ids()

            if not self.units_map:
                self._set_status("No units found", "error")
                self.create_button.setEnabled(False)
                return

            # Set up autocomplete with unit names
            unit_names = sorted(self.units_map.keys())
            completer = QCompleter(unit_names, self.unit_input)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            self.unit_input.setCompleter(completer)

            self._set_status(f"Loaded {len(unit_names)} units", "success")

        except Exception as e:
            self._set_status("Failed to load units", "error")
            QMessageBox.critical(
                self,
                "Units Load Error",
                f"Error loading units from server:\n\n{str(e)}",
            )
            self.create_button.setEnabled(False)

    def _create_label(self):
        """Create and print shipping label for bulk unit."""
        # Validate unit input
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

        if self.printer_combo.currentText() == "No printers found":
            self._set_status("No printer selected", "error")
            return

        # Disable create button during shipment
        self.create_button.setEnabled(False)

        # Get unit composite ID and fetch address
        composite_id = self.units_map[unit_name]
        self._set_status(f"Fetching address for {unit_name}...", "info")

        try:
            to_address_dict = self.server.unit_address(composite_id)
        except Exception as e:
            self._set_status("Failed to fetch unit address", "error")
            QMessageBox.critical(
                self,
                "Unit Address Error",
                f"Error fetching address for {unit_name}:\n\n{str(e)}",
            )
            self.create_button.setEnabled(True)
            return

        # Build return address dictionary
        from_address_dict = {
            "name": self.config.return_address.name,
            "street1": self.config.return_address.street1,
            "street2": self.config.return_address.street2,
            "city": self.config.return_address.city,
            "state": self.config.return_address.state,
            "zipcode": self.config.return_address.zipcode,
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
        self.shipment_worker.warning.connect(lambda msg: self._set_status(msg, "warning"))
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

        # Clear input fields for next shipment
        self.unit_input.clear()
        self.weight_input.setValue(1)

        # Focus on unit input
        self.unit_input.setFocus()

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
