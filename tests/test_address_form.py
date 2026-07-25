"""Unit tests for the shared address form widget."""

import unittest

from PySide6.QtWidgets import QApplication

from shippy_gui.core.models import (
    ParsedAddress,
    RecipientAddress,
    ReturnAddressConfig,
)
from shippy_gui.widgets.address_form import AddressForm


class AddressFormTests(unittest.TestCase):
    """Tests for form reuse between recipient and return addresses."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_recipient_form_defaults_produce_a_recipient_address(self):
        form = AddressForm()
        form.set_address(
            {
                "name": "Jane Doe",
                "street1": "123 Prison Rd",
                "city": "Huntsville",
                "state": "TX",
                "zipcode": "77340",
            }
        )

        address = form.get_address()

        self.assertIsInstance(address, RecipientAddress)
        self.assertEqual(address.name, "Jane Doe")
        self.assertIsNone(address.company)

    def test_return_form_hides_company_and_produces_return_config(self):
        form = AddressForm(
            include_company=False, subject="return", output_model=ReturnAddressConfig
        )
        form.set_address(
            ReturnAddressConfig(
                name="Inside Books Project",
                street1="827 W 12th St",
                city="Austin",
                state="TX",
                zipcode="78701",
            )
        )

        address = form.get_address()

        self.assertIsInstance(address, ReturnAddressConfig)
        self.assertTrue(form.company_input.isHidden())
        self.assertEqual(address.city, "Austin")
        self.assertIsNone(address.company)

    def test_validation_message_uses_the_configured_subject(self):
        recipient_form = AddressForm()
        return_form = AddressForm(
            include_company=False, subject="return", output_model=ReturnAddressConfig
        )

        self.assertEqual(
            recipient_form.validate_required(), "Please enter recipient name"
        )
        self.assertEqual(return_form.validate_required(), "Please enter return name")

    def test_validation_reports_each_missing_field_in_order(self):
        form = AddressForm()
        form.name_input.setText("Jane Doe")

        self.assertEqual(form.validate_required(), "Please enter street address")

        form.street1_input.setText("123 Prison Rd")
        self.assertEqual(form.validate_required(), "Please enter city")

    def test_merge_address_does_not_clear_existing_values(self):
        form = AddressForm()
        form.name_input.setText("Jane Doe")
        form.street2_input.setText("Unit 4")

        form.merge_address(
            ParsedAddress(street1="123 Prison Rd", city="Huntsville", state="TX")
        )

        self.assertEqual(form.name_input.text(), "Jane Doe")
        self.assertEqual(form.street2_input.text(), "Unit 4")
        self.assertEqual(form.street1_input.text(), "123 Prison Rd")

    def test_clear_empties_every_mapped_field(self):
        form = AddressForm()
        form.set_address(
            {
                "name": "Jane Doe",
                "company": "Unit B",
                "street1": "123 Prison Rd",
                "street2": "Apt 2",
                "city": "Huntsville",
                "state": "TX",
                "zipcode": "77340",
            }
        )

        form.clear()

        self.assertEqual(form.get_values(), {key: "" for key in form.get_values()})

    def test_missing_required_keys_reports_absent_components(self):
        missing = AddressForm.missing_required_keys(
            ParsedAddress(street1="123 Prison Rd", city="Huntsville")
        )

        self.assertEqual(missing, ["state", "zipcode"])


if __name__ == "__main__":
    unittest.main()
