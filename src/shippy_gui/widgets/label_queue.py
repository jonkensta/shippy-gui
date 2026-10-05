"""Widgets that keep volunteers from creating a label twice.

- the duplicate-label question asked before postage is bought,
- the "Label queued" dialog shown when a label was saved to print later.
"""

import html
from typing import Any, Optional, Sequence

from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QMessageBox,
    QWidget,
)

from shippy_gui.core import label_journal

DUPLICATE_TITLE = "Label Already Created"
QUEUED_TITLE = "Label queued — do not create it again"


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
