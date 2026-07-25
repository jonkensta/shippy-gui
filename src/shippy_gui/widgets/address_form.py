"""Address form widget."""

from typing import Optional, Type, Union

from PySide6.QtWidgets import QWidget, QFormLayout, QLineEdit  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import AddressBase, ParsedAddress, RecipientAddress


class AddressForm(QWidget):  # pylint: disable=too-many-instance-attributes
    """Widget for entering address details.

    Used for both the recipient address and, with ``include_company=False``,
    the return address in the settings dialog. ReturnAddressConfig and
    RecipientAddress are the same shape, so one widget serves both.
    """

    # Widget attribute name -> label fragment used in "Please enter ..." errors.
    REQUIRED_FIELDS = [
        ("name_input", "{subject} name"),
        ("street1_input", "street address"),
        ("city_input", "city"),
        ("state_input", "state"),
        ("zipcode_input", "ZIP code"),
    ]
    REQUIRED_ADDRESS_KEYS = ["street1", "city", "state", "zipcode"]

    # Map data keys to widget attribute names
    ADDRESS_FIELD_MAP = {
        "name": "name_input",
        "company": "company_input",
        "street1": "street1_input",
        "street2": "street2_input",
        "city": "city_input",
        "state": "state_input",
        "zipcode": "zipcode_input",
    }

    def __init__(
        self,
        parent=None,
        *,
        include_company: bool = True,
        subject: str = "recipient",
        output_model: Type[AddressBase] = RecipientAddress,
    ):
        """Initialize the address form.

        Args:
            parent: Parent widget.
            include_company: Whether to show the optional company field.
            subject: Noun used in validation messages ("recipient", "return").
            output_model: Model produced by :meth:`get_address`.
        """
        super().__init__(parent)
        self._include_company = include_company
        self._subject = subject
        self._output_model = output_model
        self._init_ui()

    def _init_ui(self):
        layout = QFormLayout()
        self.setLayout(layout)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(f"{self._subject.capitalize()} name")
        self.name_input.setToolTip(f"{self._subject.capitalize()}'s full name")
        layout.addRow("Name:", self.name_input)

        # Parented to self even when unused, so it never becomes a stray
        # top-level window.
        self.company_input = QLineEdit(self)
        self.company_input.setPlaceholderText("Optional")
        self.company_input.setToolTip("Company or institution name (optional)")
        if self._include_company:
            layout.addRow("Company:", self.company_input)
        else:
            self.company_input.hide()

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
        for widget_name in self.ADDRESS_FIELD_MAP.values():
            getattr(self, widget_name).clear()

    def get_values(self) -> dict[str, str]:
        """Return the stripped field values, without validating them."""
        return {
            key: getattr(self, widget_name).text().strip()
            for key, widget_name in self.ADDRESS_FIELD_MAP.items()
        }

    def get_address(self) -> AddressBase:
        """Get the address data as the configured address model."""
        values = self.get_values()
        return self._output_model(
            name=values["name"],
            company=values["company"] or None,
            street1=values["street1"],
            street2=values["street2"],
            city=values["city"],
            state=values["state"],
            zipcode=values["zipcode"],
        )

    @staticmethod
    def _as_dict(data: Union[dict, AddressBase, ParsedAddress]) -> dict:
        """Normalize supported address inputs into a plain dictionary."""
        if isinstance(data, (AddressBase, ParsedAddress)):
            return data.model_dump(exclude_none=True)
        return data

    def set_address(self, data: Union[dict, AddressBase, ParsedAddress]):
        """Populate fields from a dictionary or address model."""
        data_dict = self._as_dict(data)

        for key, widget_name in self.ADDRESS_FIELD_MAP.items():
            if key in data_dict:
                getattr(self, widget_name).setText(data_dict[key] or "")

    def merge_address(self, data: Union[dict, AddressBase, ParsedAddress]):
        """Populate only non-empty parsed values without clearing existing fields."""
        data_dict = self._as_dict(data)

        for key, widget_name in self.ADDRESS_FIELD_MAP.items():
            value = data_dict.get(key)
            if value:
                getattr(self, widget_name).setText(value)

    def validate_required(self) -> Optional[str]:
        """Validate required fields and return error message if any."""
        for field_name, label in self.REQUIRED_FIELDS:
            field = getattr(self, field_name)
            if not field.text().strip():
                return f"Please enter {label.format(subject=self._subject)}"
        return None

    @classmethod
    def missing_required_keys(
        cls, address_parts: Union[dict, AddressBase, ParsedAddress]
    ) -> list[str]:
        """Return required address keys missing from parsed components."""
        data_dict = cls._as_dict(address_parts)
        return [key for key in cls.REQUIRED_ADDRESS_KEYS if key not in data_dict]
