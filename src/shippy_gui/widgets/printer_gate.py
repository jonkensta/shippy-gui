"""The "plug in the label printer" question asked before postage is bought."""

from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from shippy_gui.widgets.shipment_controls import ShipmentControls

NO_PRINTER_TITLE = "No label printer detected"


class PrinterGateResult(str, Enum):
    """How the volunteer got past the no-printer question."""

    # A printer appeared while the question was open: print to it.
    PRINTER_FOUND = "printer_found"
    # Buy the label anyway; it is saved to Downloads\to-print\ for the watcher.
    CONTINUE_ANYWAY = "continue_anyway"
    # Do not buy anything.
    CANCELED = "canceled"


class NoPrinterDialog(QDialog):  # pylint: disable=too-few-public-methods
    """Waits for a printer to be plugged in; closes by itself when one appears.

    Relies on the controls' automatic printer scan (``printers_updated``), so
    there is a single poller for the whole window.
    """

    def __init__(self, controls: ShipmentControls, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._controls = controls
        self.result_choice = PrinterGateResult.CANCELED
        self.setWindowTitle(NO_PRINTER_TITLE)
        self.setModal(True)

        layout = QVBoxLayout(self)
        headline = QLabel(
            '<p style="font-size:16pt; font-weight:bold;">No label printer '
            "detected — plug in the printer</p>"
        )
        headline.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(headline)
        layout.addWidget(
            QLabel(
                "Plug the label printer into this laptop and turn it on. Windows "
                "can take a little while to find it; this window closes by itself "
                "and the label is created as soon as the printer is found.\n\n"
                'If you click "Continue anyway", postage is bought now and the '
                "label is saved to Downloads\\to-print\\. The label watcher prints "
                "it automatically once a printer is connected. Do NOT create the "
                "label again."
            )
        )

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.continue_button = QPushButton("Continue anyway")
        self.cancel_button = QPushButton("Cancel")
        # Enter must not buy postage without a printer by accident.
        self.continue_button.setAutoDefault(False)
        self.cancel_button.setDefault(True)
        self.continue_button.clicked.connect(self._continue_anyway)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.continue_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        controls.printers_updated.connect(self._check_printer)

    def _continue_anyway(self) -> None:
        self.result_choice = PrinterGateResult.CONTINUE_ANYWAY
        self.accept()

    def _check_printer(self) -> None:
        if self.isVisible() and self._controls.has_printers:
            self.result_choice = PrinterGateResult.PRINTER_FOUND
            self.accept()

    def done(self, arg__1: int) -> None:  # pylint: disable=invalid-name
        """Stop listening for printers once closed."""
        try:
            self._controls.printers_updated.disconnect(self._check_printer)
        except (RuntimeError, TypeError):
            pass
        super().done(arg__1)


def wait_for_printer(
    parent: Optional[QWidget], controls: ShipmentControls
) -> PrinterGateResult:
    """Return at once if a printer is ready; otherwise ask and wait for one."""
    if controls.has_printers:
        return PrinterGateResult.PRINTER_FOUND
    dialog = NoPrinterDialog(controls, parent)
    dialog.exec()
    return dialog.result_choice
