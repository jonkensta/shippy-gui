"""Google Maps autocomplete widget for Qt."""

import logging
from typing import Optional

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtCore import QStringListModel, Qt, QThread, QTimer, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QCompleter, QLineEdit  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.models import AutocompletePrediction

logger = logging.getLogger(__name__)


class GoogleMapsLookupWorker(QThread):  # pylint: disable=too-few-public-methods
    """Worker thread for Google Maps API calls."""

    results_ready = Signal(int, list)  # (request_id, list of predictions)
    error_occurred = Signal(int, str)  # (request_id, error message)

    def __init__(self, gmaps: googlemaps.Client, search_text: str, request_id: int):
        super().__init__()
        self.gmaps = gmaps
        self.search_text = search_text
        self.request_id = request_id

    def run(self):
        """Fetch autocomplete predictions from Google Maps."""
        try:
            places_autocomplete = self.gmaps.places_autocomplete(
                input_text=self.search_text, components={"country": "US"}
            )
            predictions = [
                AutocompletePrediction(
                    description=prediction["description"],
                    place_id=prediction.get("place_id"),
                    structured_formatting=prediction.get("structured_formatting"),
                    types=prediction.get("types", []),
                )
                for prediction in places_autocomplete
            ]
            self.results_ready.emit(self.request_id, predictions)
        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ) as e:
            self.error_occurred.emit(self.request_id, str(e))


class GoogleMapsCompleter(
    QCompleter
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Google Maps autocomplete completer for QLineEdit."""

    def __init__(
        self, gmaps: googlemaps.Client, debounce_delay: int = 2000, parent=None
    ):
        """Initialize the completer.

        Args:
            gmaps: Google Maps client
            debounce_delay: Delay in milliseconds before triggering search
            parent: Parent widget
        """
        super().__init__(parent)
        self.gmaps = gmaps
        self.debounce_delay = debounce_delay
        self.cache: dict[str, list[AutocompletePrediction]] = {}
        self.current_predictions: list[AutocompletePrediction] = []
        self.current_worker = None
        self.current_text = ""
        self.next_request_id = 0
        self.current_request_id = -1

        # Set up string list model for completions
        self.model = QStringListModel()
        self.setModel(self.model)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)

        # Set up debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._fetch_predictions)

    def update_completions(self, text: str):
        """Update completions based on current text.

        Args:
            text: Current text in the line edit
        """
        # Stop any existing timer
        self.debounce_timer.stop()

        # Minimum 3 characters required
        if len(text) < 3:
            self.current_predictions = []
            self.model.setStringList([])
            return

        # Check cache first
        if text in self.cache:
            self.current_predictions = self.cache[text]
            self.model.setStringList(
                [prediction.description for prediction in self.current_predictions]
            )
            # Force the popup to show when using cached results
            if self.cache[text]:
                self.complete()
            return

        # Start debounce timer
        self.current_text = text
        self.debounce_timer.start(self.debounce_delay)

    def _fetch_predictions(self):
        """Fetch predictions from Google Maps API (called after debounce)."""
        text = self.current_text

        # Assign a new request ID for this search
        request_id = self.next_request_id
        self.next_request_id += 1
        self.current_request_id = request_id

        # Note: Don't terminate existing worker - let it finish and ignore stale results
        # This is safer than terminate() which can cause crashes

        # Start new worker thread
        self.current_worker = GoogleMapsLookupWorker(self.gmaps, text, request_id)
        self.current_worker.results_ready.connect(
            lambda req_id, predictions: self._on_results_ready(
                text, req_id, predictions
            )
        )
        self.current_worker.error_occurred.connect(self._on_error)
        self.current_worker.start()

    def _on_results_ready(
        self,
        text: str,
        request_id: int,
        predictions: list[AutocompletePrediction],
    ):
        """Handle results from worker thread.

        Args:
            text: The search text these predictions are for
            request_id: Request ID that generated these results
            predictions: List of address predictions
        """
        # Ignore stale results from old requests
        if request_id != self.current_request_id:
            return

        # Cache the results
        self.cache[text] = predictions

        # Update model if this is still the current text
        if text == self.current_text:
            self.current_predictions = predictions
            descriptions = [prediction.description for prediction in predictions]
            self.model.setStringList(descriptions)
            self._log_duplicate_descriptions(descriptions)
            # Force the popup to show since the model was updated asynchronously
            if predictions:
                self.complete()

    def _on_error(self, request_id: int, error_message: str):
        """Handle error from worker thread.

        Args:
            request_id: Request ID that generated this error
            error_message: Error message
        """
        # Ignore stale errors from old requests
        if request_id != self.current_request_id:
            return

        # Clear completions on error
        self.current_predictions = []
        self.model.setStringList([])
        logger.warning("Google Maps API error: %s", error_message)

    def get_prediction_for_text(
        self, description: str
    ) -> Optional[AutocompletePrediction]:
        """Return the first stored prediction matching the activated text."""
        matches = [
            prediction
            for prediction in self.current_predictions
            if prediction.description == description
        ]
        if len(matches) > 1:
            logger.debug("Duplicate autocomplete descriptions for '%s'", description)
        return matches[0] if matches else None

    @staticmethod
    def _log_duplicate_descriptions(descriptions: list[str]) -> None:
        """Log duplicate descriptions to aid future collision handling."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for description in descriptions:
            if description in seen:
                duplicates.add(description)
                continue
            seen.add(description)
        for description in duplicates:
            logger.debug("Duplicate autocomplete description returned: %s", description)


def setup_google_maps_autocomplete(
    line_edit: QLineEdit, gmaps: googlemaps.Client, debounce_delay: int = 2000
) -> GoogleMapsCompleter:
    """Set up Google Maps autocomplete on a QLineEdit.

    Args:
        line_edit: The line edit to add autocomplete to
        gmaps: Google Maps client
        debounce_delay: Delay in milliseconds before triggering search

    Returns:
        The completer instance
    """
    completer = GoogleMapsCompleter(gmaps, debounce_delay, line_edit)
    line_edit.setCompleter(completer)

    # Connect text changed signal to update completions
    line_edit.textChanged.connect(completer.update_completions)

    return completer
