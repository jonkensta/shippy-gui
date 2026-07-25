"""Unit tests for the purchased-but-unresolved shipment journal."""

import os
import tempfile
import unittest

from shippy_gui.core.pending_shipments import (
    PENDING_SHIPMENTS_FILENAME,
    PendingShipmentJournal,
    journal_path_for,
)


class PendingShipmentJournalTests(unittest.TestCase):
    """Tests for recording and clearing unresolved shipments."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.path = os.path.join(self._tempdir.name, PENDING_SHIPMENTS_FILENAME)
        self.journal = PendingShipmentJournal(self.path)

    def test_journal_path_sits_beside_the_config(self):
        self.assertEqual(
            journal_path_for("/etc/shippy/config.ini"),
            os.path.join("/etc/shippy", PENDING_SHIPMENTS_FILENAME),
        )

    def test_empty_when_no_file_exists(self):
        self.assertEqual(self.journal.pending(), [])

    def test_record_then_clear_round_trip(self):
        self.journal.record("shp_1", tracking_code="TRACK1")

        pending = self.journal.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].shipment_id, "shp_1")
        self.assertEqual(pending[0].tracking_code, "TRACK1")

        self.journal.clear("shp_1")
        self.assertEqual(self.journal.pending(), [])

    def test_record_survives_a_new_journal_instance(self):
        """The whole point: the record outlives the process."""
        self.journal.record("shp_1")

        reopened = PendingShipmentJournal(self.path)

        self.assertEqual([e.shipment_id for e in reopened.pending()], ["shp_1"])

    def test_recording_the_same_shipment_twice_does_not_duplicate(self):
        self.journal.record("shp_1")
        self.journal.record("shp_1", tracking_code="TRACK1")

        pending = self.journal.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].tracking_code, "TRACK1")

    def test_clearing_an_unknown_shipment_is_harmless(self):
        self.journal.record("shp_1")

        self.journal.clear("shp_missing")

        self.assertEqual([e.shipment_id for e in self.journal.pending()], ["shp_1"])

    def test_corrupt_journal_is_treated_as_empty(self):
        """A broken journal must never stop the operator printing labels."""
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("this is not json")

        self.assertEqual(self.journal.pending(), [])

    def test_unexpected_json_shape_is_treated_as_empty(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write('{"shipment_id": "shp_1"}')

        self.assertEqual(self.journal.pending(), [])

    def test_malformed_entries_are_surfaced_not_silently_dropped(self):
        """A damaged entry may be the only trace of unrefunded postage."""
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write('[{"tracking_code": "T"}, {"shipment_id": "shp_1"}]')

        # The readable entry is still returned so it can be reconciled...
        self.assertEqual([e.shipment_id for e in self.journal.pending()], ["shp_1"])
        # ...and a copy is left behind so the operator can be warned.
        self.assertTrue(os.path.exists(self.journal.corrupt_path))

    def test_a_clean_journal_leaves_no_corrupt_copy(self):
        self.journal.record("shp_1")

        self.journal.pending()

        self.assertFalse(os.path.exists(self.journal.corrupt_path))

    def test_unparseable_journal_is_moved_aside(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("this is not json")

        self.assertEqual(self.journal.pending(), [])
        self.assertTrue(os.path.exists(self.journal.corrupt_path))
        self.assertFalse(os.path.exists(self.path))

    def test_record_reports_whether_it_persisted(self):
        self.assertTrue(self.journal.record("shp_1"))

        unwritable = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "missing-dir", "journal.json")
        )
        self.assertFalse(unwritable.record("shp_1"))

    def test_blank_ids_are_ignored(self):
        self.journal.record("")

        self.assertEqual(self.journal.pending(), [])

    def test_write_failure_does_not_raise(self):
        """A read-only directory must not break label printing."""
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "missing-dir", "journal.json")
        )

        journal.record("shp_1")

        self.assertEqual(journal.pending(), [])


if __name__ == "__main__":
    unittest.main()
