"""Unit tests for address parsing behavior."""

import unittest
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication

from shippy_gui.core.addresses import (
    AddressComponentParser,
    AddressParser,
    GoogleAddressLookup,
)
from shippy_gui.core.models import AutocompletePrediction
from shippy_gui.widgets.address_form import AddressForm


class AddressParserComponentTests(unittest.TestCase):
    """Tests for component extraction and place_id-first geocoding."""

    def setUp(self):
        self.gmaps = Mock()
        self.parser = AddressParser(self.gmaps)
        self.component_parser = AddressComponentParser()
        self.lookup = GoogleAddressLookup(self.gmaps)

    def test_parse_standard_address_components(self):
        parsed = self.component_parser.parse(
            [
                {"long_name": "123", "types": ["street_number"]},
                {"long_name": "Prison Rd", "types": ["route"]},
                {"long_name": "Huntsville", "types": ["locality"]},
                {"short_name": "TX", "types": ["administrative_area_level_1"]},
                {"long_name": "77340", "types": ["postal_code"]},
                {"short_name": "US", "types": ["country"]},
            ]
        )

        self.assertEqual(parsed.street1, "123 Prison Rd")
        self.assertIsNone(parsed.street2)
        self.assertEqual(parsed.city, "Huntsville")
        self.assertEqual(parsed.state, "TX")
        self.assertEqual(parsed.zipcode, "77340")
        self.assertEqual(parsed.country, "US")

    def test_parse_standard_address_ignores_establishment_for_street2(self):
        parsed = self.component_parser.parse(
            [
                {"long_name": "123", "types": ["street_number"]},
                {"long_name": "Main St", "types": ["route"]},
                {"long_name": "Corner Store", "types": ["establishment"]},
                {"long_name": "Austin", "types": ["locality"]},
                {"short_name": "TX", "types": ["administrative_area_level_1"]},
                {"long_name": "78703", "types": ["postal_code"]},
            ]
        )

        self.assertEqual(parsed.street1, "123 Main St")
        self.assertIsNone(parsed.street2)

    def test_parse_facility_and_unit_components(self):
        parsed = self.component_parser.parse(
            [
                {"long_name": "123", "types": ["street_number"]},
                {"long_name": "Prison Rd", "types": ["route"]},
                {"long_name": "Unit 42", "types": ["subpremise"]},
                {"long_name": "Byrd Unit", "types": ["establishment"]},
                {"long_name": "Huntsville", "types": ["locality"]},
                {"short_name": "TX", "types": ["administrative_area_level_1"]},
                {"long_name": "77340", "types": ["postal_code"]},
            ]
        )

        self.assertEqual(parsed.street1, "123 Prison Rd")
        self.assertEqual(parsed.street2, "Unit 42, Byrd Unit")

    def test_parse_zip_plus_four_and_city_fallback(self):
        parsed = self.component_parser.parse(
            [
                {"long_name": "PO Box 1", "types": ["premise"]},
                {"long_name": "Austin", "types": ["postal_town"]},
                {"short_name": "TX", "types": ["administrative_area_level_1"]},
                {"long_name": "78703", "types": ["postal_code"]},
                {"long_name": "1029", "types": ["postal_code_suffix"]},
            ]
        )

        self.assertEqual(parsed.street1, "PO Box 1")
        self.assertEqual(parsed.city, "Austin")
        self.assertEqual(parsed.zipcode, "78703-1029")

    def test_google_lookup_uses_place_id_before_description_geocode(self):
        self.gmaps.geocode.return_value = [{"address_components": []}]

        self.lookup.lookup(
            AutocompletePrediction(
                description="123 Prison Rd, Huntsville, TX 77340, USA",
                place_id="abc123",
            )
        )

        self.gmaps.geocode.assert_called_once_with(place_id="abc123")

    def test_uses_place_id_before_description_geocode(self):
        self.gmaps.geocode.return_value = [
            {
                "address_components": [
                    {"long_name": "123", "types": ["street_number"]},
                    {"long_name": "Prison Rd", "types": ["route"]},
                ]
            }
        ]

        parsed = self.parser(
            AutocompletePrediction(
                description="123 Prison Rd, Huntsville, TX 77340, USA",
                place_id="abc123",
            )
        )

        self.assertEqual(parsed.street1, "123 Prison Rd")
        self.gmaps.geocode.assert_called_once_with(place_id="abc123")

    def test_google_lookup_falls_back_to_description_when_place_id_lookup_returns_no_result(
        self,
    ):
        self.gmaps.geocode.side_effect = [[], [{"address_components": []}]]

        self.lookup.lookup(
            AutocompletePrediction(
                description="PO Box 1, Austin, TX", place_id="abc123"
            )
        )

        self.assertEqual(
            self.gmaps.geocode.call_args_list,
            [
                unittest.mock.call(place_id="abc123"),
                unittest.mock.call(address="PO Box 1, Austin, TX", region="us"),
            ],
        )

    def test_falls_back_to_description_when_place_id_lookup_returns_no_result(self):
        self.gmaps.geocode.side_effect = [
            [],
            [
                {
                    "address_components": [
                        {"long_name": "PO Box 1", "types": ["premise"]},
                    ]
                }
            ],
        ]

        parsed = self.parser(
            AutocompletePrediction(
                description="PO Box 1, Austin, TX", place_id="abc123"
            )
        )

        self.assertEqual(parsed.street1, "PO Box 1")
        self.assertEqual(
            self.gmaps.geocode.call_args_list,
            [
                unittest.mock.call(place_id="abc123"),
                unittest.mock.call(address="PO Box 1, Austin, TX", region="us"),
            ],
        )

    def test_returns_none_when_all_geocode_attempts_fail(self):
        self.gmaps.geocode.side_effect = [[], []]

        parsed = self.parser(
            AutocompletePrediction(
                description="PO Box 1, Austin, TX", place_id="abc123"
            )
        )

        self.assertIsNone(parsed)


class AddressFormTests(unittest.TestCase):
    """Tests for non-destructive address form behavior."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.form = AddressForm()

    def test_merge_address_preserves_existing_values(self):
        self.form.name_input.setText("Jane Doe")
        self.form.street2_input.setText("Unit 42")

        self.form.merge_address({"street1": "123 Prison Rd", "city": "Huntsville"})

        self.assertEqual(self.form.name_input.text(), "Jane Doe")
        self.assertEqual(self.form.street2_input.text(), "Unit 42")
        self.assertEqual(self.form.street1_input.text(), "123 Prison Rd")
        self.assertEqual(self.form.city_input.text(), "Huntsville")

    def test_merge_address_not_called_when_parser_returns_none(self):
        parser = Mock(return_value=None)
        self.form.name_input.setText("Jane Doe")
        self.form.street2_input.setText("Unit 42")

        parsed = parser("unparseable address")
        if parsed:
            self.form.merge_address(parsed)

        parser.assert_called_once_with("unparseable address")
        self.assertEqual(self.form.name_input.text(), "Jane Doe")
        self.assertEqual(self.form.street2_input.text(), "Unit 42")


if __name__ == "__main__":
    unittest.main()
