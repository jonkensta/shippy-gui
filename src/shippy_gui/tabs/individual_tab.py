"""Individual shipping mode tab."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class IndividualTab(QWidget):
    """Tab for individual inmate shipping."""

    def __init__(self, parent=None):
        """Initialize the individual shipping tab."""
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Placeholder content
        label = QLabel("Individual Shipping Mode")
        label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(label)

        placeholder = QLabel("This tab will contain individual inmate shipping functionality.")
        layout.addWidget(placeholder)

        layout.addStretch()
        self.setLayout(layout)
