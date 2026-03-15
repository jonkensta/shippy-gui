"""Shipment controls widget."""

from typing import Optional
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QFormLayout,
    QHBoxLayout,
    QSpinBox,
    QComboBox,
    QPushButton,
)
from PySide6.QtCore import Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import WEIGHT_MIN_LBS, WEIGHT_MAX_LBS, DEFAULT_WEIGHT_LBS
from shippy_gui.printing.models import PrinterInfo
from shippy_gui.printing.printer_manager import (
    get_available_printers,
)


class ShipmentControls(QWidget):
    """Widget for weight and printer selection."""

    NO_PRINTERS_LABEL = "No printers found"
    PRINTER_TOOLTIP = (
        "Choose the label printer you want to use.\n"
        "This list only shows USB label printers that are plugged in and turned on.\n"
        "The printer name must end with the USB ID, such as 20d1:7008.\n"
        "If you just plugged in or turned on a printer, click Refresh.\n"
        "If no printers appear, check that the printer is plugged in, turned on, and ready."
    )
    REFRESH_TOOLTIP = (
        "Click Refresh to scan again for USB label printers.\n"
        "Use this after you plug in a printer or turn one on.\n"
        "You do not need to restart the program."
    )

    create_requested = Signal()

    def __init__(self, default_weight: int = DEFAULT_WEIGHT_LBS, parent=None):
        super().__init__(parent)
        self._default_weight = default_weight
        self._controls_enabled = True
        self._has_printers = False
        self._init_ui()
        self.refresh_printers()

    def _init_ui(self):
        layout = QFormLayout()
        self.setLayout(layout)

        self.weight_input = QSpinBox()
        self.weight_input.setRange(WEIGHT_MIN_LBS, WEIGHT_MAX_LBS)
        self.weight_input.setValue(self._default_weight)
        self.weight_input.setSuffix(" lbs")
        self.weight_input.setToolTip(
            f"Package weight in pounds ({WEIGHT_MIN_LBS}-{WEIGHT_MAX_LBS} lbs)"
        )
        layout.addRow("Weight:", self.weight_input)

        self.printer_combo = QComboBox()
        self.printer_combo.setToolTip(self.PRINTER_TOOLTIP)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip(self.REFRESH_TOOLTIP)
        self.refresh_button.clicked.connect(self.refresh_printers)
        printer_row = QHBoxLayout()
        printer_row.addWidget(self.printer_combo, 1)
        printer_row.addWidget(self.refresh_button)
        layout.addRow("Printer:", printer_row)

        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.setToolTip(
            "Purchase postage, download label, and print to selected printer.\n"
            "Hold Shift + Click to choose printer via system dialog.\n"
            "Label will be automatically refunded if printing fails."
        )
        self.create_button.clicked.connect(self.create_requested.emit)
        layout.addRow(self.create_button)

    def refresh_printers(self):
        """Refresh the printer list while preserving selection when possible."""
        printers = get_available_printers()
        selected_printer = self.printer_name
        self.printer_combo.clear()

        if not printers:
            self._has_printers = False
            self.printer_combo.addItem(self.NO_PRINTERS_LABEL)
            self._update_enabled_state()
            return

        self._has_printers = True
        for printer in printers:
            self.printer_combo.addItem(printer.system_name, printer)

        printer_names = [printer.system_name for printer in printers]

        if selected_printer and selected_printer in printer_names:
            index = printer_names.index(selected_printer)
            self.printer_combo.setCurrentIndex(index)
            self._update_enabled_state()
            return

        default_index = next(
            (index for index, printer in enumerate(printers) if printer.is_default),
            None,
        )
        if default_index is not None:
            index = default_index
            self.printer_combo.setCurrentIndex(index)
        else:
            self.printer_combo.setCurrentIndex(0)
        self._update_enabled_state()

    @property
    def weight_lbs(self) -> int:
        """Get current weight value."""
        return self.weight_input.value()

    @property
    def printer_name(self) -> str:
        """Get selected printer name."""
        printer = self.selected_printer
        if printer is None:
            return self.printer_combo.currentText()
        return printer.system_name

    @property
    def selected_printer(self) -> Optional[PrinterInfo]:
        """Get selected printer metadata."""
        printer = self.printer_combo.currentData()
        return printer if isinstance(printer, PrinterInfo) else None

    def set_enabled(self, enabled: bool):
        """Enable or disable controls."""
        self._controls_enabled = enabled
        self._update_enabled_state()

    def _update_enabled_state(self):
        """Apply enabled state while respecting printer availability."""
        self.weight_input.setEnabled(self._controls_enabled)
        self.printer_combo.setEnabled(self._controls_enabled and self._has_printers)
        self.refresh_button.setEnabled(self._controls_enabled)
        self.create_button.setEnabled(self._controls_enabled and self._has_printers)

    def reset(self):
        """Reset controls after successful shipment.

        Note: Weight is intentionally NOT reset since users often
        ship multiple packages of the same weight in succession.
        """
        # Weight is preserved between shipments

    def validate(self) -> Optional[str]:
        """Validate controls and return error message if any."""
        if self.printer_combo.currentText() == self.NO_PRINTERS_LABEL:
            return "No printer selected"
        return None
