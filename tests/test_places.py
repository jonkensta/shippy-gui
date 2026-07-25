"""Unit tests for the headless Google Places lookup service."""

import subprocess
import sys
import unittest
from unittest.mock import Mock

from shippy_gui.core.models import AutocompletePrediction
from shippy_gui.core.places import GooglePlacesService


class GooglePlacesServiceTests(unittest.TestCase):
    """Tests for prediction fetching, caching, and matching."""

    def setUp(self):
        self.gmaps = Mock()
        self.places = GooglePlacesService(self.gmaps)

    def test_is_searchable_requires_three_characters(self):
        self.assertFalse(GooglePlacesService.is_searchable("12"))
        self.assertTrue(GooglePlacesService.is_searchable("123"))

    def test_fetch_maps_raw_google_payload_to_models(self):
        self.gmaps.places_autocomplete.return_value = [
            {
                "description": "123 Main St, Austin, TX",
                "place_id": "place_1",
                "types": ["street_address"],
            },
            {"description": "456 Elm St, Austin, TX"},
        ]

        predictions = self.places.fetch("123 Main")

        self.gmaps.places_autocomplete.assert_called_once_with(
            input_text="123 Main", components={"country": "US"}
        )
        self.assertEqual(len(predictions), 2)
        self.assertEqual(predictions[0].place_id, "place_1")
        self.assertEqual(predictions[0].types, ["street_address"])
        self.assertIsNone(predictions[1].place_id)

    def test_cache_round_trip(self):
        self.assertIsNone(self.places.get_cached("123 Main"))

        predictions = [AutocompletePrediction(description="123 Main St")]
        self.places.store("123 Main", predictions)

        self.assertEqual(self.places.get_cached("123 Main"), predictions)

    def test_cached_empty_result_is_distinguishable_from_a_miss(self):
        """An empty cached list must not be re-fetched as if it were a miss."""
        self.places.store("zzz", [])

        self.assertEqual(self.places.get_cached("zzz"), [])
        self.assertIsNotNone(self.places.get_cached("zzz"))

    def test_find_by_description_returns_first_match(self):
        first = AutocompletePrediction(description="123 Main St", place_id="a")
        second = AutocompletePrediction(description="123 Main St", place_id="b")
        other = AutocompletePrediction(description="456 Elm St", place_id="c")

        match = GooglePlacesService.find_by_description(
            [first, second, other], "123 Main St"
        )

        self.assertEqual(match, first)

    def test_find_by_description_returns_none_when_absent(self):
        predictions = [AutocompletePrediction(description="456 Elm St")]

        self.assertIsNone(
            GooglePlacesService.find_by_description(predictions, "123 Main St")
        )

    def test_places_service_does_not_import_qt(self):
        """The lookup layer must be usable without a GUI toolkit."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import shippy_gui.core.places; "
                "sys.exit(1 if any(m.startswith('PySide6') for m in sys.modules) else 0)",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"core.places pulled in PySide6: {result.stderr.decode()}",
        )


if __name__ == "__main__":
    unittest.main()
