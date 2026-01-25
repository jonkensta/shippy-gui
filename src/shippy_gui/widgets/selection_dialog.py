"""Dialog for selecting from multiple options."""

# pylint: disable=duplicate-code  # Common button layout pattern

from typing import Any

from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
)
from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module


class SelectionDialog(QDialog):  # pylint: disable=too-few-public-methods
    """Dialog for selecting one option from multiple choices."""

    def __init__(
        self, title: str, message: str, options: list[tuple[str, Any]], parent=None
    ):
        """Initialize the selection dialog.

        Args:
            title: Dialog window title
            message: Instruction message to display
            options: List of (display_text, data) tuples
            parent: Parent widget
        """
        super().__init__(parent)
        self.selected_data = None
        self._init_ui(title, message, options)

    def _init_ui(self, title: str, message: str, options: list[tuple[str, Any]]):
        """Initialize the user interface."""
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout()

        # Message label
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        # List widget
        self.list_widget = QListWidget()
        for display_text, data in options:
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, data)
            self.list_widget.addItem(item)

        # Select first item by default
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        # Enable double-click to select
        self.list_widget.itemDoubleClicked.connect(self._on_select)

        layout.addWidget(self.list_widget)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        select_button = QPushButton("Select")
        select_button.clicked.connect(self._on_select)
        select_button.setDefault(True)
        button_layout.addWidget(select_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _on_select(self):
        """Handle selection and close dialog."""
        current_item = self.list_widget.currentItem()
        if current_item:
            self.selected_data = current_item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def get_selected(self):
        """Get the selected data.

        Returns:
            The data associated with the selected item, or None if cancelled.
        """
        return self.selected_data
