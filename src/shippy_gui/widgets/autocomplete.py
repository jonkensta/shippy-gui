"""Google Maps autocomplete widget for Qt.

This module is a Qt adapter: debouncing, the worker thread, stale-response
handling, and the popup live here. The Google call and its cache live in
``core.places`` so they can be exercised without a QApplication.
"""

import logging
from typing import Optional

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtCore import QStringListModel, Qt, QThread, QTimer, Signal  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QCompleter, QLineEdit  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.constants import LOOKUP_SHUTDOWN_WAIT_MS
from shippy_gui.core.models import AutocompletePrediction
from shippy_gui.core.places import GooglePlacesService

logger = logging.getLogger(__name__)


class GoogleMapsLookupWorker(QThread):  # pylint: disable=too-few-public-methods
    """Worker thread for Google Maps API calls."""

    results_ready = Signal(int, list)  # (request_id, list of predictions)
    error_occurred = Signal(int, str)  # (request_id, error message)

    def __init__(self, places: GooglePlacesService, search_text: str, request_id: int):
        super().__init__()
        self.places = places
        self.search_text = search_text
        self.request_id = request_id

    def run(self):
        """Fetch autocomplete predictions from Google Maps."""
        try:
            predictions = self.places.fetch(self.search_text)
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
        self.places = GooglePlacesService(gmaps)
        self.debounce_delay = debounce_delay
        self.current_predictions: list[AutocompletePrediction] = []
        self.current_worker = None
        # Every started worker is held here until it finishes. Dropping the
        # last reference to a running QThread destroys it mid-run, which Qt
        # turns into a qFatal abort - not a catchable exception.
        self._active_workers: set[GoogleMapsLookupWorker] = set()
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

        if not self.places.is_searchable(text):
            self.current_predictions = []
            self.model.setStringList([])
            return

        cached = self.places.get_cached(text)
        if cached is not None:
            self._show_predictions(cached)
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

        # Don't terminate the existing worker - terminate() can corrupt state.
        # It is left to finish and its stale results are ignored, which means
        # it must stay referenced until then; see _active_workers.
        worker = GoogleMapsLookupWorker(self.places, text, request_id)
        worker.results_ready.connect(
            lambda req_id, predictions: self._on_results_ready(
                text, req_id, predictions
            )
        )
        worker.error_occurred.connect(self._on_error)
        worker.finished.connect(self._retire_finished_workers)

        self._active_workers.add(worker)
        self.current_worker = worker
        worker.start()

    def _retire_finished_workers(self) -> None:
        """Release workers that have finished running."""
        for worker in {w for w in self._active_workers if w.isFinished()}:
            self._active_workers.discard(worker)
            worker.deleteLater()

    def wait_for_workers(self, timeout_ms: int = LOOKUP_SHUTDOWN_WAIT_MS) -> None:
        """Block until in-flight lookups finish, so shutdown does not abort."""
        for worker in list(self._active_workers):
            if worker.isRunning():
                worker.wait(timeout_ms)
        self._retire_finished_workers()

    def _show_predictions(self, predictions: list[AutocompletePrediction]) -> None:
        """Publish predictions to the popup model."""
        self.current_predictions = predictions
        self.model.setStringList([prediction.description for prediction in predictions])
        # Force the popup to show since the model may have changed asynchronously
        if predictions:
            self.complete()

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

        self.places.store(text, predictions)

        # Update model if this is still the current text
        if text == self.current_text:
            self._show_predictions(predictions)

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
        return self.places.find_by_description(self.current_predictions, description)


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
