"""Manual shipping mode tab."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class ManualTab(QWidget):
    """Tab for manual address shipping."""

    def __init__(self, parent=None):
        """Initialize the manual shipping tab."""
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Placeholder content
        label = QLabel("Manual Shipping Mode")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(label)

        placeholder = QLabel("This tab will contain manual address entry functionality.")
        layout.addWidget(placeholder)

        layout.addStretch()
        self.setLayout(layout)
