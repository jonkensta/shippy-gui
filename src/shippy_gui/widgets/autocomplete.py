"""Google Maps autocomplete widget for Qt."""

import googlemaps
from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtWidgets import QCompleter, QLineEdit
from PySide6.QtCore import Qt, QStringListModel


class GoogleMapsLookupWorker(QThread):
    """Worker thread for Google Maps API calls."""

    results_ready = Signal(int, list)  # (request_id, list of address strings)
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
                prediction["description"] for prediction in places_autocomplete
            ]
            self.results_ready.emit(self.request_id, predictions)
        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ) as e:
            self.error_occurred.emit(self.request_id, str(e))


class GoogleMapsCompleter(QCompleter):
    """Google Maps autocomplete completer for QLineEdit."""

    def __init__(self, gmaps: googlemaps.Client, debounce_delay: int = 2000, parent=None):
        """Initialize the completer.

        Args:
            gmaps: Google Maps client
            debounce_delay: Delay in milliseconds before triggering search
            parent: Parent widget
        """
        super().__init__(parent)
        self.gmaps = gmaps
        self.debounce_delay = debounce_delay
        self.cache = {}
        self.current_worker = None
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
            self.model.setStringList([])
            return

        # Check cache first
        if text in self.cache:
            self.model.setStringList(self.cache[text])
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
            lambda req_id, predictions: self._on_results_ready(text, req_id, predictions)
        )
        self.current_worker.error_occurred.connect(self._on_error)
        self.current_worker.start()

    def _on_results_ready(self, text: str, request_id: int, predictions: list[str]):
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
            self.model.setStringList(predictions)

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
        self.model.setStringList([])
        print(f"Google Maps API error: {error_message}")


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
