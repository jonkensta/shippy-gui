"""Headless Google Places autocomplete lookup and caching.

The Qt completer owns debouncing, threading, and the popup. Everything that
talks to Google - and the cache in front of it - lives here so it can be
tested without a QApplication.
"""

import logging
from typing import Optional

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error

from shippy_gui.core.models import AutocompletePrediction

logger = logging.getLogger(__name__)

# Google's autocomplete is not useful below this many characters.
MIN_AUTOCOMPLETE_LENGTH = 3


class GooglePlacesService:
    """Fetch and cache Google Places autocomplete predictions."""

    def __init__(self, gmaps: googlemaps.Client):
        self.gmaps = gmaps
        self._cache: dict[str, list[AutocompletePrediction]] = {}

    @staticmethod
    def is_searchable(text: str) -> bool:
        """Report whether text is long enough to be worth querying."""
        return len(text) >= MIN_AUTOCOMPLETE_LENGTH

    def get_cached(self, text: str) -> Optional[list[AutocompletePrediction]]:
        """Return previously fetched predictions for text, if any."""
        return self._cache.get(text)

    def store(self, text: str, predictions: list[AutocompletePrediction]) -> None:
        """Cache predictions for a search string."""
        self._cache[text] = predictions

    def fetch(self, text: str) -> list[AutocompletePrediction]:
        """Fetch predictions from Google Places.

        Raises:
            googlemaps.exceptions.ApiError: On API-level failures.
            googlemaps.exceptions.Timeout: On request timeout.
            googlemaps.exceptions.TransportError: On transport failures.
        """
        raw_predictions = self.gmaps.places_autocomplete(
            input_text=text, components={"country": "US"}
        )
        return [
            AutocompletePrediction(
                description=prediction["description"],
                place_id=prediction.get("place_id"),
                structured_formatting=prediction.get("structured_formatting"),
                types=prediction.get("types", []),
            )
            for prediction in raw_predictions
        ]

    @staticmethod
    def find_by_description(
        predictions: list[AutocompletePrediction], description: str
    ) -> Optional[AutocompletePrediction]:
        """Return the first prediction whose description matches exactly."""
        matches = [
            prediction
            for prediction in predictions
            if prediction.description == description
        ]
        if len(matches) > 1:
            logger.debug("Duplicate autocomplete descriptions for '%s'", description)
        return matches[0] if matches else None
