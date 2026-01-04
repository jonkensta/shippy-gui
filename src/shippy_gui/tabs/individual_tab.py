"""Individual shipping mode tab."""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt

from shippy_gui.printing.printer_manager import get_available_printers, get_default_printer


class IndividualTab(QWidget):
    """Tab for individual inmate shipping."""

    def __init__(self, parent=None):
        """Initialize the individual shipping tab."""
        super().__init__(parent)
        self._init_ui()
        self._load_printers()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Form layout for inputs
        form_layout = QFormLayout()

        # Barcode/ID input
        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("TEX-12345678-0, FED-12345678-0, or numeric ID")
        form_layout.addRow("Barcode, Inmate ID, or Request ID:", self.barcode_input)

        # Weight input
        self.weight_input = QSpinBox()
        self.weight_input.setRange(1, 70)
        self.weight_input.setValue(1)
        self.weight_input.setSuffix(" lbs")
        form_layout.addRow("Weight:", self.weight_input)

        # Printer selector
        self.printer_combo = QComboBox()
        form_layout.addRow("Printer:", self.printer_combo)

        layout.addLayout(form_layout)

        # Create label button
        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._create_label)
        layout.addWidget(self.create_button)

        # Status label
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

    def _create_label(self):
        """Create and print shipping label."""
        # Get inputs
        barcode = self.barcode_input.text().strip()
        weight = self.weight_input.value()
        printer = self.printer_combo.currentText()

        # Validate inputs
        if not barcode:
            self._set_status("Please enter a barcode, inmate ID, or request ID", "error")
            return

        if printer == "No printers found":
            self._set_status("No printer selected", "error")
            return

        # TODO: Implement shipment workflow in next step
        self._set_status(f"Creating label for {barcode}, {weight} lbs, printer: {printer}...", "info")

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
