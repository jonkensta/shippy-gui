"""Unified shipping tab with inmate lookup and manual address entry."""

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
)
from PySide6.QtCore import Qt

from shippy_gui.printing.printer_manager import get_available_printers, get_default_printer


class ShippingTab(QWidget):
    """Tab for unified shipping with optional inmate/address lookup."""

    def __init__(self, parent=None):
        """Initialize the shipping tab."""
        super().__init__(parent)
        self._init_ui()
        self._load_printers()

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
        inmate_layout.addWidget(self.inmate_input, 1)
        self.inmate_lookup_button = QPushButton("Lookup")
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
        address_search_layout.addWidget(self.address_search_input, 1)
        self.address_search_button = QPushButton("Search")
        self.address_search_button.clicked.connect(self._search_address)
        address_search_layout.addWidget(self.address_search_button)
        lookup_layout.addLayout(address_search_layout)

        lookup_group.setLayout(lookup_layout)
        layout.addWidget(lookup_group)

        # Recipient Address Section
        address_group = QGroupBox("Recipient Address")
        address_form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Recipient name")
        address_form.addRow("Name:", self.name_input)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Optional")
        address_form.addRow("Company:", self.company_input)

        self.street1_input = QLineEdit()
        address_form.addRow("Street 1:", self.street1_input)

        self.street2_input = QLineEdit()
        self.street2_input.setPlaceholderText("Optional")
        address_form.addRow("Street 2:", self.street2_input)

        self.city_input = QLineEdit()
        address_form.addRow("City:", self.city_input)

        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("TX")
        self.state_input.setMaxLength(2)
        address_form.addRow("State:", self.state_input)

        self.zipcode_input = QLineEdit()
        self.zipcode_input.setPlaceholderText("78703")
        address_form.addRow("ZIP Code:", self.zipcode_input)

        address_group.setLayout(address_form)
        layout.addWidget(address_group)

        # Shipment Details Section
        shipment_form = QFormLayout()

        self.weight_input = QSpinBox()
        self.weight_input.setRange(1, 70)
        self.weight_input.setValue(1)
        self.weight_input.setSuffix(" lbs")
        shipment_form.addRow("Weight:", self.weight_input)

        self.printer_combo = QComboBox()
        shipment_form.addRow("Printer:", self.printer_combo)

        layout.addLayout(shipment_form)

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

    def _lookup_inmate(self):
        """Look up inmate and populate address fields."""
        inmate_id = self.inmate_input.text().strip()
        if not inmate_id:
            self._set_status("Please enter a barcode, ID, or request ID", "error")
            return

        # TODO: Implement inmate lookup workflow
        self._set_status(f"Looking up inmate: {inmate_id}...", "info")

    def _search_address(self):
        """Search Google Maps and populate address fields."""
        search_query = self.address_search_input.text().strip()
        if not search_query:
            self._set_status("Please enter an address to search", "error")
            return

        # TODO: Implement Google Maps search workflow
        self._set_status(f"Searching for address: {search_query}...", "info")

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

        # TODO: Implement shipment workflow
        self._set_status("Creating label...", "info")

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
