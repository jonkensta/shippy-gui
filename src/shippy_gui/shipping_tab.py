"""Unified shipping tab with manual address entry."""

# pylint: disable=duplicate-code  # Intentional patterns shared with settings_dialog

from pathlib import Path
from typing import Optional, Any

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLineEdit,
    QLabel,
    QMessageBox,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.printing.printer_manager import (
    print_image_with_dialog,
)
from shippy_gui.core.config_manager import ConfigManager
from shippy_gui.core.constants import STATUS_COLORS
from shippy_gui.core.addresses import AddressParser
from shippy_gui.core.services import ShipmentService
from shippy_gui.widgets.autocomplete import setup_google_maps_autocomplete
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.shipment_controls import ShipmentControls
from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShippingTab(QWidget):
    """Tab for unified shipping with address lookup."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, config_path: Optional[str] = None, parent=None):
        """Initialize the shipping tab."""
        super().__init__(parent)
        self._config_manager = ConfigManager(config_path)

        self.gmaps: Optional[googlemaps.Client] = None
        self.address_parser: Optional[AddressParser] = None
        self.shipment_service: Optional[ShipmentService] = None
        self.logo_path: Optional[str] = None
        self.shipment_worker: Optional[ShipmentWorker] = None

        # UI Components
        self.address_search_input: Optional[QLineEdit] = None
        self.address_form: Optional[AddressForm] = None
        self.shipment_controls: Optional[ShipmentControls] = None
        self.status_label: Optional[QLabel] = None

        self._init_api_clients()
        self._load_logo()
        self._init_ui()
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

        # Initialize Shipment Service
        self.shipment_service = ShipmentService(config.easypost.apikey)

    def _load_logo(self):
        """Load logo image if available."""
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        if logo_path.exists():
            self.logo_path = str(logo_path)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Quick Lookup Section
        lookup_group = QGroupBox("Quick Lookup")
        lookup_layout = QVBoxLayout()
        address_search_layout = QHBoxLayout()
        address_search_layout.addWidget(QLabel("Address Search:"))
        self.address_search_input = QLineEdit()
        self.address_search_input.setPlaceholderText("Start typing address...")
        self.address_search_input.setToolTip("Search for addresses using Google Maps")
        address_search_layout.addWidget(self.address_search_input, 1)
        lookup_layout.addLayout(address_search_layout)
        lookup_group.setLayout(lookup_layout)
        layout.addWidget(lookup_group)

        # Recipient Address Section
        address_group = QGroupBox("Recipient Address")
        address_layout = QVBoxLayout()
        self.address_form = AddressForm()
        address_layout.addWidget(self.address_form)
        address_group.setLayout(address_layout)
        layout.addWidget(address_group)

        # Shipment Details Section
        self.shipment_controls = ShipmentControls()
        self.shipment_controls.create_requested.connect(self._create_label)
        layout.addWidget(self.shipment_controls)

        # Status Label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def _setup_autocomplete(self):
        """Set up Google Maps autocomplete on address search field."""
        if not self.gmaps:
            return

        completer = setup_google_maps_autocomplete(
            self.address_search_input, self.gmaps, debounce_delay=500
        )
        completer.activated.connect(self._load_address)

    def _load_address(self, selected_address: Optional[str] = None):
        """Parse selected address and populate address fields."""
        if not self.address_search_input:
            return

        search_query = selected_address or self.address_search_input.text().strip()
        if not search_query:
            self._set_status("Please enter an address to search", "error")
            return

        if not self.address_parser:
            QMessageBox.critical(self, "Error", "Google Maps not configured.")
            return

        self._set_status(f"Parsing address: {search_query}...", "info")

        try:
            address_parts = self.address_parser(search_query)
            if not address_parts:
                self._set_status("Could not parse address", "error")
                return

            if self.address_form:
                self.address_form.clear()
                self.address_form.set_address(address_parts)

            if self.address_search_input:
                QTimer.singleShot(0, self.address_search_input.clear)

            # Check for missing required components in parsed address
            required = ["street1", "city", "state", "zipcode"]
            missing = [f for f in required if f not in address_parts]
            if missing:
                self._set_status(f"Missing: {', '.join(missing)}", "warning")
            else:
                self._set_status("Address loaded successfully", "success")

        except Exception as e:  # pylint: disable=broad-exception-caught
            self._set_status("Address search failed", "error")
            QMessageBox.critical(self, "Error", str(e))

    def _create_label(self):
        """Create and print shipping label."""
        if not self.address_form or not self.shipment_controls:
            return

        validation_error = (
            self.address_form.validate_required() or self.shipment_controls.validate()
        )
        if validation_error:
            self._set_status(validation_error, "error")
            return

        if not self.shipment_service or not self.config:
            QMessageBox.critical(self, "Error", "Services not configured.")
            return

        self.shipment_controls.set_enabled(False)

        # Check for Shift key to enable print dialog
        use_dialog = (
            QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        ) == Qt.KeyboardModifier.ShiftModifier

        # Create and start worker thread
        self.shipment_worker = ShipmentWorker(
            shipment_service=self.shipment_service,
            from_address=self.config.return_address,
            to_address=self.address_form.get_address(),
            weight_lbs=self.shipment_controls.weight_lbs,
            printer_name=self.shipment_controls.printer_name,
            logo_path=self.logo_path,
            use_dialog=use_dialog,
        )

        self.shipment_worker.progress.connect(lambda msg: self._set_status(msg, "info"))
        self.shipment_worker.warning.connect(
            lambda msg: self._set_status(msg, "warning")
        )
        self.shipment_worker.success.connect(self._on_shipment_success)
        self.shipment_worker.error.connect(self._on_shipment_error)
        self.shipment_worker.finished.connect(self._on_shipment_finished)
        self.shipment_worker.label_ready.connect(self._on_label_ready)
        self.shipment_worker.start()

    def _on_label_ready(self, image, printer_name: str, shipment: Any):
        """Handle label ready for printing via system dialog."""
        if not self.shipment_service:
            return

        result = print_image_with_dialog(
            image, self, preferred_printer_name=printer_name
        )

        if result == "printed":
            self._on_shipment_success(
                f"Label printed! Tracking: {shipment.tracking_code}"
            )
        elif result in ("canceled", "failed"):
            self._refund_shipment(shipment, f"Print {result}")

    def _refund_shipment(self, shipment, reason: str) -> None:
        """Request a refund for a shipment."""
        if not self.shipment_service:
            return

        self._set_status("Requesting refund...", "warning")
        try:
            self.shipment_service.refund_shipment(shipment.id)
            self._set_status(f"{reason}. Refunded.", "warning")
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._set_status("Refund failed", "error")
            QMessageBox.critical(self, "Refund Error", str(e))

    def _on_shipment_success(self, message: str):
        """Handle successful shipment."""
        self._set_status(message, "success")
        if self.address_form:
            self.address_form.clear()
        if self.shipment_controls:
            self.shipment_controls.reset()
        if self.address_search_input:
            self.address_search_input.setFocus()

    def _on_shipment_error(self, message: str):
        """Handle shipment error."""
        self._set_status("Shipment failed", "error")
        QMessageBox.critical(self, "Shipment Error", message)

    def _on_shipment_finished(self):
        """Handle worker thread completion."""
        if self.shipment_controls:
            self.shipment_controls.set_enabled(True)
        self.shipment_worker = None

    def _set_status(self, message: str, status_type: str = "info"):
        """Set status message with color coding."""
        if not self.status_label:
            return
        color = STATUS_COLORS.get(status_type, STATUS_COLORS["info"])
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
