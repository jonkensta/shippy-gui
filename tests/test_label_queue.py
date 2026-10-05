"""Tests for the duplicate guard wording, queued-label dialog and indicator."""

import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from shippy_gui.core import label_journal
from shippy_gui.core.models import RecipientAddress
from shippy_gui.widgets.label_queue import (
    PendingLabelsDialog,
    PendingLabelsIndicator,
    build_duplicate_box,
    build_label_queued_box,
)

from journal_fakes import install_fake_journal, make_record


def wait_until(predicate, timeout_s=5.0):
    """Process Qt events until ``predicate()`` holds."""
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the indicator")
        app.processEvents()
        time.sleep(0.01)


class DuplicateQuestionTests(unittest.TestCase):
    """The question asked before buying a second label for a recipient."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_queued_wording(self):
        text = label_journal.duplicate_question([make_record(status="queued")])
        self.assertEqual(
            text,
            "A label for Jane Doe, 123 Prison Rd, Huntsville, TX is already "
            "queued \u2014 it will print automatically when the printer works "
            "(tracking 9400OLD). Create another label anyway?",
        )

    def test_check_printer_wording(self):
        text = label_journal.duplicate_question([make_record(status="check_printer")])
        self.assertIn(
            "is already waiting at the printer: check the printer before "
            "reprinting (tracking 9400OLD)",
            text,
        )

    def test_printed_wording_uses_local_time(self):
        printed = datetime.now().replace(hour=14, minute=5).timestamp()
        text = label_journal.duplicate_question(
            [make_record(status="printed", created=printed, updated=printed)]
        )
        self.assertIn("is already printed at 14:05 (tracking 9400OLD)", text)

    def test_older_labels_show_the_date(self):
        printed = (datetime.now() - timedelta(days=1)).replace(hour=8, minute=7)
        text = label_journal.duplicate_question(
            [make_record(status="printed", updated=printed.timestamp())]
        )
        self.assertIn(f"printed at {printed.strftime('%b %d')} 08:07", text)

    def test_newest_label_is_named_and_others_counted(self):
        now = time.time()
        older = make_record(tracking_code="OLD", created=now - 3 * 3600)
        newer = make_record(tracking_code="NEW", status="check_printer", created=now)
        text = label_journal.duplicate_question([newer, older])
        self.assertIn("(tracking NEW)", text)
        self.assertIn("1 other label(s)", text)

    def test_box_defaults_to_no(self):
        box = build_duplicate_box(None, [make_record()])
        self.assertEqual(box.windowTitle(), "Label Already Created")
        self.assertIs(box.defaultButton(), box.button(QMessageBox.StandardButton.No))
        self.assertIs(box.escapeButton(), box.button(QMessageBox.StandardButton.No))
        self.assertIn("Create another label anyway?", box.text())

    def test_identity_joins_both_street_lines(self):
        journal = install_fake_journal(self)
        identity = label_journal.identity_for(
            RecipientAddress(
                name="John Roe #123",
                street1="1 Unit Rd",
                street2="Bldg 4",
                city="Gatesville",
                state="TX",
                zipcode="76528",
            )
        )
        self.assertEqual(
            identity.recipient_key,
            journal.recipient_key(
                "John Roe #123", "1 Unit Rd Bldg 4", "Gatesville", "TX", "76528"
            ),
        )
        self.assertEqual(
            identity.recipient_label, "John Roe #123, 1 Unit Rd, Gatesville, TX"
        )

    def test_slow_journal_does_not_block_the_check(self):
        journal = install_fake_journal(self)
        release = threading.Event()
        self.addCleanup(release.set)

        def stuck(*_args, **_kwargs):
            release.wait(5)
            return [make_record()]

        journal.find_duplicates = stuck
        identity = label_journal.LabelIdentity("key", "Jane")
        started = time.monotonic()
        with self.assertLogs("shippy_gui.core.label_journal", "WARNING"):
            records = label_journal.find_duplicates(identity, timeout_s=0.1)
        self.assertEqual(records, [])
        self.assertLess(time.monotonic() - started, 2.0)


class LabelQueuedDialogTests(unittest.TestCase):
    """The dialog shown when a label was saved to print later."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_is_big_bold_and_keeps_instructions(self):
        details = (
            "The label did NOT print: no printer\n\nBefore you print that file "
            "by hand, or refund this shipment in EasyPost, DELETE it from "
            "C:\\Downloads\\to-print first"
        )
        box = build_label_queued_box(
            None, "Jane Doe, 123 Prison Rd, Huntsville, TX", "9400NEW", details
        )

        self.assertEqual(
            box.windowTitle(), "Label queued \u2014 do not create it again"
        )
        text = box.text()
        self.assertIn("font-weight:bold", text)
        self.assertIn("font-size:18pt", text)
        self.assertIn("Recipient: Jane Doe, 123 Prison Rd, Huntsville, TX", text)
        self.assertIn("Tracking: 9400NEW", text)
        self.assertIn("It will print automatically when the printer works.", text)
        self.assertIn("Do NOT create this label again.", text)
        self.assertIn("DELETE it from", box.informativeText())
        self.assertIn("C:\\Downloads\\to-print", box.informativeText())

    def test_recipient_is_html_escaped(self):
        box = build_label_queued_box(None, "A <b> & Co", "T1", "x")
        self.assertIn("A &lt;b&gt; &amp; Co", box.text())


class PendingLabelsIndicatorTests(unittest.TestCase):
    """The "Waiting to print: N" status-bar indicator."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_when_nothing_waits(self):
        indicator = PendingLabelsIndicator(fetch=list)
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 0)
        self.assertTrue(indicator.isHidden())

    def test_shows_count_and_updates(self):
        pending = [make_record(), make_record(tracking_code="9400TWO")]
        indicator = PendingLabelsIndicator(fetch=lambda: list(pending))

        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.text(), "Waiting to print: 2")
        self.assertFalse(indicator.isHidden())

        pending.clear()
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 0)
        self.assertTrue(indicator.isHidden())

    def test_failed_read_keeps_last_count(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] > 1:
                raise OSError("journal locked")
            return [make_record()]

        indicator = PendingLabelsIndicator(fetch=flaky)
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        with self.assertLogs("shippy_gui.widgets.label_queue", "ERROR"):
            indicator.refresh()
            wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.text(), "Waiting to print: 1")

    def test_slow_read_does_not_block_or_pile_up(self):
        release = threading.Event()
        self.addCleanup(release.set)
        calls = {"n": 0}

        def slow():
            calls["n"] += 1
            release.wait(5)
            return [make_record()]

        indicator = PendingLabelsIndicator(fetch=slow)
        started = time.monotonic()
        indicator.refresh()
        indicator.refresh()  # skipped: a read is already running
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(indicator.busy)

        release.set()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(indicator.count, 1)

    def test_timer_refreshes_periodically(self):
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return []

        indicator = PendingLabelsIndicator(fetch=fetch, interval_ms=20)
        indicator.start()
        try:
            wait_until(lambda: calls["n"] >= 3)
        finally:
            indicator._timer.stop()  # pylint: disable=protected-access

    def test_default_fetch_reads_the_journal(self):
        journal = install_fake_journal(self)
        journal.pending = [make_record()]
        indicator = PendingLabelsIndicator()
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 1)

    def test_click_opens_details(self):
        indicator = PendingLabelsIndicator(fetch=lambda: [make_record()])
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        with patch(
            "shippy_gui.widgets.label_queue.PendingLabelsDialog.exec"
        ) as mock_exec:
            indicator.click()
        mock_exec.assert_called_once_with()

    def test_details_dialog_lists_labels(self):
        queued_at = datetime.now().replace(hour=9, minute=41).timestamp()
        dialog = PendingLabelsDialog(
            [
                make_record(updated=queued_at, file="/tmp/x.png"),
                make_record(tracking_code="9400TWO", status="check_printer"),
            ]
        )
        table = dialog.table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(
            [table.horizontalHeaderItem(i).text() for i in range(4)],
            ["Recipient", "Tracking", "Status", "Queued at"],
        )
        self.assertEqual(
            table.item(0, 0).text(), "Jane Doe, 123 Prison Rd, Huntsville, TX"
        )
        self.assertEqual(table.item(0, 1).text(), "9400OLD")
        self.assertEqual(table.item(0, 2).text(), "Queued - prints automatically")
        self.assertEqual(table.item(0, 3).text(), "09:41")
        self.assertEqual(table.item(1, 2).text(), "Check the printer")


if __name__ == "__main__":
    unittest.main()
