"""Unit tests for Google Maps autocomplete worker lifetime and caching."""

import time
import unittest
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication, QLineEdit

from shippy_gui.widgets.autocomplete import GoogleMapsCompleter


class AutocompleteWorkerLifetimeTests(unittest.TestCase):
    """A running QThread must stay referenced or Qt aborts the process."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _completer(self, lookup_delay: float = 0.0):
        gmaps = Mock()

        def lookup(**kwargs):
            time.sleep(lookup_delay)
            return [{"description": kwargs["input_text"], "place_id": "p"}]

        gmaps.places_autocomplete.side_effect = lookup
        line_edit = QLineEdit()
        completer = GoogleMapsCompleter(gmaps, debounce_delay=0, parent=line_edit)
        # Keep the parent alive for the duration of the test.
        completer._test_line_edit = line_edit
        return completer

    def test_overlapping_lookups_keep_the_earlier_worker_referenced(self):
        """Starting a second lookup must not drop a running first one."""
        completer = self._completer(lookup_delay=0.5)

        completer.current_text = "123 Main"
        completer._fetch_predictions()
        first = completer.current_worker

        completer.current_text = "123 Main St"
        completer._fetch_predictions()

        self.assertIsNot(completer.current_worker, first)
        self.assertIn(first, completer._active_workers)
        self.assertTrue(first.isRunning())

        completer.wait_for_workers()

    def test_finished_workers_are_released(self):
        completer = self._completer()

        completer.current_text = "123 Main"
        completer._fetch_predictions()
        completer.wait_for_workers()

        self.assertEqual(completer._active_workers, set())

    def test_wait_for_workers_is_safe_with_nothing_running(self):
        completer = self._completer()

        completer.wait_for_workers()

        self.assertEqual(completer._active_workers, set())

    def test_short_text_does_not_start_a_worker(self):
        completer = self._completer()

        completer.update_completions("12")

        self.assertEqual(completer._active_workers, set())
        self.assertEqual(completer.current_predictions, [])


if __name__ == "__main__":
    unittest.main()
