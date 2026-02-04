"""Shipment controls widget."""

from typing import Optional
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QFormLayout,
    QSpinBox,
    QComboBox,
    QPushButton,
)
from PySide6.QtCore import Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import WEIGHT_MIN_LBS, WEIGHT_MAX_LBS
from shippy_gui.printing.printer_manager import (
    get_available_printers,
    get_default_printer,
)


class ShipmentControls(QWidget):
    """Widget for weight and printer selection."""

    NO_PRINTERS_LABEL = "No printers found"

    create_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_printers()

    def _init_ui(self):
        layout = QFormLayout()
        self.setLayout(layout)

        self.weight_input = QSpinBox()
        self.weight_input.setRange(WEIGHT_MIN_LBS, WEIGHT_MAX_LBS)
        self.weight_input.setValue(WEIGHT_MIN_LBS)
        self.weight_input.setSuffix(" lbs")
        self.weight_input.setToolTip(
            f"Package weight in pounds ({WEIGHT_MIN_LBS}-{WEIGHT_MAX_LBS} lbs)"
        )
        layout.addRow("Weight:", self.weight_input)

        self.printer_combo = QComboBox()
        self.printer_combo.setToolTip(
            "Select printer for shipping label (4x6 label size)"
        )
        layout.addRow("Printer:", self.printer_combo)

        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.setToolTip(
            "Purchase postage, download label, and print to selected printer.\n"
            "Hold Shift + Click to choose printer via system dialog.\n"
            "Label will be automatically refunded if printing fails."
        )
        self.create_button.clicked.connect(self.create_requested.emit)
        layout.addRow(self.create_button)

    def _load_printers(self):
        """Load available printers into the combo box."""
        printers = get_available_printers()

        if not printers:
            self.printer_combo.addItem(self.NO_PRINTERS_LABEL)
            self.create_button.setEnabled(False)
            return

        self.printer_combo.addItems(printers)

        # Select default printer if available
        default_printer = get_default_printer()
        if default_printer and default_printer in printers:
            index = printers.index(default_printer)
            self.printer_combo.setCurrentIndex(index)

    @property
    def weight_lbs(self) -> int:
        """Get current weight value."""
        return self.weight_input.value()

    @property
    def printer_name(self) -> str:
        """Get selected printer name."""
        return self.printer_combo.currentText()

    def set_enabled(self, enabled: bool):
        """Enable or disable controls."""
        self.weight_input.setEnabled(enabled)
        self.printer_combo.setEnabled(enabled)
        self.create_button.setEnabled(enabled)

    def reset(self):
        """Reset controls to defaults."""
        self.weight_input.setValue(WEIGHT_MIN_LBS)

    def validate(self) -> Optional[str]:
        """Validate controls and return error message if any."""
        if self.printer_combo.currentText() == self.NO_PRINTERS_LABEL:
            return "No printer selected"
        return None
