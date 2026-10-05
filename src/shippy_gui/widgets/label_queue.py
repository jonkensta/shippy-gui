"""Widgets that keep volunteers from creating a label twice.

- the duplicate-label question asked before postage is bought,
- the "Label queued" dialog shown when a label was saved to print later,
- the "Waiting to print: N" status-bar indicator and its details dialog.
"""

import html
import logging
import threading
from typing import Any, Callable, Iterable, Optional, Sequence

from PySide6.QtCore import QTimer, Qt, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from shippy_gui.core import label_journal

logger = logging.getLogger(__name__)

DUPLICATE_TITLE = "Label Already Created"
QUEUED_TITLE = "Label queued — do not create it again"
PENDING_TITLE = "Labels Waiting To Print"

# How often the status-bar indicator re-reads the journal.
PENDING_REFRESH_MS = 10_000

STATUS_NAMES = {
    label_journal.STATUS_QUEUED: "Queued - prints automatically",
    label_journal.STATUS_CHECK_PRINTER: "Check the printer",
    label_journal.STATUS_PURCHASED: "Bought, not printed yet",
}


def build_duplicate_box(
    parent: Optional[QWidget], records: Sequence[Any]
) -> QMessageBox:
    """The "already created" question; No is the default answer."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(DUPLICATE_TITLE)
    box.setText(label_journal.duplicate_question(records))
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    return box


def confirm_duplicate_label(parent: Optional[QWidget], records: Sequence[Any]) -> bool:
    """Ask whether to create another label; True only on an explicit Yes."""
    box = build_duplicate_box(parent, records)
    return box.exec() == QMessageBox.StandardButton.Yes


def build_label_queued_box(
    parent: Optional[QWidget], recipient_label: str, tracking: str, details: str
) -> QMessageBox:
    """The big, bold "Label queued" dialog for a label saved to print later."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(QUEUED_TITLE)
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(
        '<p style="font-size:18pt; font-weight:bold;">Label queued — do '
        "not create it again</p>"
        '<p style="font-size:14pt; font-weight:bold;">'
        f"Recipient: {html.escape(recipient_label)}<br>"
        f"Tracking: {html.escape(tracking)}</p>"
        '<p style="font-size:14pt; font-weight:bold;">It will print '
        "automatically when the printer works.</p>"
        '<p style="font-size:16pt; font-weight:bold; color:#CC0000;">Do NOT '
        "create this label again.</p>"
    )
    # The existing instructions (delete from to-print/ before printing by hand
    # or refunding) stay visible below the headline.
    box.setInformativeText(html.escape(details).replace("\n", "<br>"))
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    return box


def show_label_queued(
    parent: Optional[QWidget], recipient_label: str, tracking: str, details: str
) -> None:
    """Show the "Label queued" dialog and wait for the volunteer to close it."""
    build_label_queued_box(parent, recipient_label, tracking, details).exec()


class PendingLabelsDialog(QDialog):  # pylint: disable=too-few-public-methods
    """List the labels that are bought but still waiting to print."""

    COLUMNS = ("Recipient", "Tracking", "Status", "Queued at")

    def __init__(self, records: Sequence[Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(PENDING_TITLE)
        self.resize(720, 300)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "These labels are already bought. Do NOT create them again: "
                "queued labels print automatically when the printer works."
            )
        )
        self.table = QTableWidget(len(records), len(self.COLUMNS), self)
        self.table.setHorizontalHeaderLabels(list(self.COLUMNS))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for row, record in enumerate(records):
            status = getattr(record, "status", "")
            cells = (
                record.recipient_label,
                record.tracking_code,
                STATUS_NAMES.get(status, status),
                label_journal.format_time(record.updated or record.created),
            )
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(str(text)))
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PendingLabelsIndicator(QPushButton):
    """Status-bar "Waiting to print: N" button, hidden when nothing is waiting.

    The journal is read on a background thread (at most one read at a time),
    so a slow journal never freezes the UI; the result comes back through a
    queued signal.
    """

    _fetched = Signal(object)  # list of records, or None when the read failed

    def __init__(
        self,
        fetch: Callable[[], Iterable[Any]] = label_journal.pending_labels,
        interval_ms: int = PENDING_REFRESH_MS,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._fetch = fetch
        self._records: list[Any] = []
        self._in_flight = False
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Labels already bought that have not printed yet")
        self.setStyleSheet("color: #CC0000; font-weight: bold;")
        self.hide()
        self._fetched.connect(self._apply)
        self.clicked.connect(self.show_details)
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)

    @property
    def count(self) -> int:
        """How many labels are waiting to print (as of the last read)."""
        return len(self._records)

    @property
    def records(self) -> list[Any]:
        """The labels waiting to print (as of the last read)."""
        return list(self._records)

    @property
    def busy(self) -> bool:
        """Whether a journal read is still running."""
        return self._in_flight

    def start(self) -> None:
        """Read the journal now and then every interval."""
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        """Re-read the journal in the background (skipped if a read is running)."""
        if self._in_flight:
            return
        self._in_flight = True
        threading.Thread(
            target=self._fetch_in_background, name="pending-labels", daemon=True
        ).start()

    def _fetch_in_background(self) -> None:
        records: Optional[list[Any]]
        try:
            records = list(self._fetch())
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("Could not read the labels waiting to print")
            records = None
        try:
            self._fetched.emit(records)
        except RuntimeError:
            pass  # The window closed while the journal was being read.

    def _apply(self, records: Optional[list[Any]]) -> None:
        self._in_flight = False
        if records is None:
            return
        self._records = records
        self.setText(f"Waiting to print: {len(records)}")
        self.setVisible(bool(records))

    def show_details(self) -> None:
        """Open the list of labels waiting to print."""
        PendingLabelsDialog(self._records, self.window()).exec()
