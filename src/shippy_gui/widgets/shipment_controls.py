"""Shipment controls widget."""

import logging
import threading
from typing import Callable, Optional
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QPushButton,
)
from PySide6.QtCore import QTimer, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import (
    DEFAULT_WEIGHT_LBS,
    PRINTER_POLL_MS,
    STATUS_COLORS,
    WEIGHT_MAX_LBS,
    WEIGHT_MIN_LBS,
)
from shippy_gui.printing.models import PrinterInfo
from shippy_gui.printing.printer_manager import (
    get_available_printers,
)

logger = logging.getLogger(__name__)


class ShipmentControls(QWidget):  # pylint: disable=too-many-instance-attributes
    """Widget for weight and printer selection.

    Once ``start_printer_polling()`` is called, the printer list and the status
    line below it update themselves every ``PRINTER_POLL_MS``. Discovery runs on
    a background thread (at most one at a time) and is paused while the
    controls are disabled, i.e. while a label is being bought and printed.
    """

    NO_PRINTERS_LABEL = "No printers found"
    PRINTER_READY_TEXT = "Label printer ready"
    NO_PRINTER_TEXT = "No label printer detected - plug in the printer and turn it on"
    PRINTER_TOOLTIP = (
        "Choose the label printer you want to use.\n"
        "This list only shows USB label printers that are plugged in and turned on.\n"
        "It updates by itself a few seconds after you plug in or turn on a printer.\n"
        "If no printers appear, check that the printer is plugged in, turned on, and ready."
    )
    REFRESH_TOOLTIP = (
        "Click Refresh to scan again for USB label printers right away.\n"
        "The list also updates by itself every few seconds.\n"
        "You do not need to restart the program."
    )

    create_requested = Signal()
    # Emitted after every printer scan (manual or automatic) has been applied.
    printers_updated = Signal()
    # Background scan result: list of PrinterInfo, or None when it failed.
    _polled = Signal(object)

    def __init__(
        self,
        default_weight: int = DEFAULT_WEIGHT_LBS,
        parent=None,
        *,
        discover: Optional[Callable[[], list[PrinterInfo]]] = None,
        poll_interval_ms: int = PRINTER_POLL_MS,
    ):
        super().__init__(parent)
        self._default_weight = default_weight
        self._discover = discover
        self._controls_enabled = True
        self._has_printers = False
        self._poll_in_flight = False
        self._polled.connect(self._apply_polled)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(poll_interval_ms)
        self._poll_timer.timeout.connect(self.poll_printers)
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

        self.printer_status_label = QLabel()
        layout.addRow(self.printer_status_label)

        self.create_button = QPushButton("Create Label")
        self.create_button.setDefault(True)
        self.create_button.setToolTip(
            "Purchase postage, download label, and print to selected printer.\n"
            "Hold Shift + Click to choose printer via system dialog.\n"
            "If no printer can take the label, it is saved to print later "
            "(postage is not refunded)."
        )
        self.create_button.clicked.connect(self.create_requested.emit)
        layout.addRow(self.create_button)

    def refresh_printers(self):
        """Scan for printers now (on the UI thread) and apply the result."""
        self._apply_printers(self._scan())

    def _scan(self) -> list[PrinterInfo]:
        # Looked up at call time so tests can patch get_available_printers.
        return (self._discover or get_available_printers)()

    def start_printer_polling(self) -> None:
        """Re-scan for printers in the background every poll interval."""
        self._poll_timer.start()

    def stop_printer_polling(self) -> None:
        """Stop the automatic re-scan."""
        self._poll_timer.stop()

    def poll_printers(self) -> None:
        """Start one background scan, unless one is running or a label is in progress."""
        if self._poll_in_flight or not self._controls_enabled:
            return
        self._poll_in_flight = True
        threading.Thread(
            target=self._poll_in_background, name="printer-poll", daemon=True
        ).start()

    def _poll_in_background(self) -> None:
        printers: Optional[list[PrinterInfo]]
        try:
            printers = list(self._scan())
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Background printer scan failed")
            printers = None
        try:
            self._polled.emit(printers)
        except RuntimeError:
            pass  # The window closed while the scan was running.

    def _apply_polled(self, printers: Optional[list[PrinterInfo]]) -> None:
        self._poll_in_flight = False
        # A label started while the scan ran: leave the printer choice alone.
        if printers is None or not self._controls_enabled:
            return
        self._apply_printers(printers)

    def _apply_printers(self, printers: list[PrinterInfo]) -> None:
        """Show ``printers``, keeping the selection when it is still there."""
        current = [
            self.printer_combo.itemData(index)
            for index in range(self.printer_combo.count())
        ]
        # Rebuilding an unchanged list would close an open drop-down every scan.
        if printers and current == printers:
            self.printers_updated.emit()
            return

        selected_printer = self.printer_name
        self.printer_combo.clear()

        if not printers:
            self._has_printers = False
            self.printer_combo.addItem(self.NO_PRINTERS_LABEL)
            self._update_enabled_state()
            self.printers_updated.emit()
            return

        self._has_printers = True
        for printer in printers:
            self.printer_combo.addItem(printer.system_name, printer)

        printer_names = [printer.system_name for printer in printers]

        if selected_printer and selected_printer in printer_names:
            index = printer_names.index(selected_printer)
        else:
            index = next(
                (index for index, printer in enumerate(printers) if printer.is_default),
                0,
            )
        self.printer_combo.setCurrentIndex(index)
        self._update_enabled_state()
        self.printers_updated.emit()

    @property
    def has_printers(self) -> bool:
        """Whether a usable label printer was found by the last scan."""
        return self._has_printers

    @property
    def weight_lbs(self) -> int:
        """Get current weight value."""
        return self.weight_input.value()

    @property
    def printer_name(self) -> str:
        """Get selected printer name ("" when no printer was found)."""
        printer = self.selected_printer
        if printer is None:
            return ""
        return printer.system_name

    @property
    def selected_printer(self) -> Optional[PrinterInfo]:
        """Get selected printer metadata."""
        printer = self.printer_combo.currentData()
        return printer if isinstance(printer, PrinterInfo) else None

    def set_enabled(self, enabled: bool):
        """Enable or disable controls (disabled also pauses printer polling)."""
        self._controls_enabled = enabled
        self._update_enabled_state()

    def _update_enabled_state(self):
        """Apply enabled state while respecting printer availability."""
        self.weight_input.setEnabled(self._controls_enabled)
        self.printer_combo.setEnabled(self._controls_enabled and self._has_printers)
        self.refresh_button.setEnabled(self._controls_enabled)
        # Creating a label without a printer is allowed: the volunteer is asked
        # first and may continue anyway (the label is saved to print later).
        self.create_button.setEnabled(self._controls_enabled)
        self._update_printer_status()

    def _update_printer_status(self) -> None:
        if self._has_printers:
            text = f"{self.PRINTER_READY_TEXT}: {self.printer_name}"
            color = STATUS_COLORS["success"]
        else:
            text = self.NO_PRINTER_TEXT
            color = STATUS_COLORS["error"]
        self.printer_status_label.setText(text)
        self.printer_status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def reset(self):
        """Reset controls after successful shipment.

        Note: Weight is intentionally NOT reset since users often
        ship multiple packages of the same weight in succession.
        """
        # Weight is preserved between shipments

    def validate(self) -> Optional[str]:
        """Validate controls and return error message if any.

        A missing printer is not an error here: the shipment flow asks the
        volunteer to plug one in, or to continue and print the label later.
        """
        return None
