"""Address form widget."""

from typing import Optional
from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import RecipientAddress


class AddressForm(QWidget):
    """Widget for entering recipient address details."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout()
        self.setLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Recipient name")
        self.name_input.setToolTip("Recipient's full name")
        layout.addRow("Name:", self.name_input)

        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Optional")
        self.company_input.setToolTip("Company or institution name (optional)")
        layout.addRow("Company:", self.company_input)

        self.street1_input = QLineEdit()
        self.street1_input.setToolTip("Street address line 1 (required)")
        layout.addRow("Street 1:", self.street1_input)

        self.street2_input = QLineEdit()
        self.street2_input.setPlaceholderText("Optional")
        self.street2_input.setToolTip("Apartment, suite, unit, etc. (optional)")
        layout.addRow("Street 2:", self.street2_input)

        self.city_input = QLineEdit()
        self.city_input.setToolTip("City name (required)")
        layout.addRow("City:", self.city_input)

        self.state_input = QLineEdit()
        self.state_input.setPlaceholderText("TX")
        self.state_input.setMaxLength(2)
        self.state_input.setToolTip("Two-letter state code (e.g., TX, CA, NY)")
        layout.addRow("State:", self.state_input)

        self.zipcode_input = QLineEdit()
        self.zipcode_input.setPlaceholderText("78703")
        self.zipcode_input.setToolTip("5-digit ZIP code (required)")
        layout.addRow("ZIP Code:", self.zipcode_input)

    def clear(self):
        """Clear all fields."""
        self.name_input.clear()
        self.company_input.clear()
        self.street1_input.clear()
        self.street2_input.clear()
        self.city_input.clear()
        self.state_input.clear()
        self.zipcode_input.clear()

    def get_address(self) -> RecipientAddress:
        """Get the address data as a RecipientAddress model."""
        return RecipientAddress(
            name=self.name_input.text().strip(),
            company=self.company_input.text().strip() or None,
            street1=self.street1_input.text().strip(),
            street2=self.street2_input.text().strip() or "",
            city=self.city_input.text().strip(),
            state=self.state_input.text().strip(),
            zipcode=self.zipcode_input.text().strip(),
        )

    def set_address(self, data: dict):
        """Populate fields from a dictionary."""
        if "street1" in data:
            self.street1_input.setText(data["street1"])
        if "street2" in data:
            self.street2_input.setText(data.get("street2", ""))
        if "city" in data:
            self.city_input.setText(data["city"])
        if "state" in data:
            self.state_input.setText(data["state"])
        if "zipcode" in data:
            self.zipcode_input.setText(data["zipcode"])

    def validate_required(self) -> Optional[str]:
        """Validate required fields and return error message if any."""
        required_fields = [
            ("Please enter recipient name", self.name_input),
            ("Please enter street address", self.street1_input),
            ("Please enter city", self.city_input),
            ("Please enter state", self.state_input),
            ("Please enter ZIP code", self.zipcode_input),
        ]

        for message, field in required_fields:
            if not field.text().strip():
                return message
        return None
