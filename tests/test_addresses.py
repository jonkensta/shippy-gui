"""Unit tests for address parsing behavior."""

import unittest
from unittest.mock import Mock

from shippy_gui.core.addresses import AddressParser
from shippy_gui.core.models import AutocompletePrediction


class AddressParserComponentTests(unittest.TestCase):
    """Tests for component extraction and place_id-first geocoding."""

    def setUp(self):
        self.gmaps = Mock()
        self.parser = AddressParser(self.gmaps)

    def test_parse_standard_address_components(self):
        parsed = self.parser.parse_address_components(
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

    def test_parse_facility_and_unit_components(self):
        parsed = self.parser.parse_address_components(
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
        parsed = self.parser.parse_address_components(
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


if __name__ == "__main__":
    unittest.main()
