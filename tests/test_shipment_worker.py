"""Unit tests for the shipment worker's print and refund behavior."""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.pending_shipments import PendingShipmentJournal
from shippy_gui.core.shipment_workflow import (
    PreparedLabel,
    ShipmentPreparationError,
)
from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShipmentWorkerTests(unittest.TestCase):
    """Tests that run ShipmentWorker.run() directly, without a thread."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.shipment_service = Mock()
        self.worker = ShipmentWorker(
            shipment_service=self.shipment_service,
            from_address=ReturnAddressConfig(
                name="IBP",
                street1="827 W 12th St",
                city="Austin",
                state="TX",
                zipcode="78701",
            ),
            to_address=RecipientAddress(
                name="Jane Doe",
                street1="123 Prison Rd",
                city="Huntsville",
                state="TX",
                zipcode="77340",
            ),
            weight_lbs=2,
            printer_name="Alpha 20d1:7008",
        )
        self.shipment = Mock(id="shp_123")
        self.shipment.tracking_code = "TRACK123"
        self.prepared = PreparedLabel(
            shipment=self.shipment, image=Image.new("RGB", (10, 10), "white")
        )

        self.emitted: dict[str, list] = {
            "success": [],
            "error": [],
            "refunded": [],
            "label_ready": [],
        }
        self.worker.success.connect(self.emitted["success"].append)
        self.worker.error.connect(self.emitted["error"].append)
        self.worker.refunded.connect(self.emitted["refunded"].append)
        self.worker.label_ready.connect(
            lambda *args: self.emitted["label_ready"].append(args)
        )

    def _prepare_label_stub(self, _workflow_input, **kwargs):
        """Stand in for prepare_label, honouring the on_purchase contract.

        The real workflow invokes on_purchase the instant postage is bought,
        before the label is downloaded; the stub must do the same or the
        journal behaviour under test is not exercised.
        """
        on_purchase = kwargs.get("on_purchase")
        if on_purchase is not None:
            on_purchase(self.prepared.shipment)
        return self.prepared

    def test_successful_print_emits_tracking_code(self):
        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch("shippy_gui.workers.shipment_worker.print_image"),
        ):
            self.worker.run()

        self.assertEqual(len(self.emitted["success"]), 1)
        self.assertIn("TRACK123", self.emitted["success"][0])
        self.shipment_service.refund_shipment.assert_not_called()

    def test_print_failure_refunds_inside_the_worker(self):
        """The refund must happen in run(), not be deferred to the UI thread."""
        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=RuntimeError("printer offline"),
            ),
        ):
            self.worker.run()

        # Already refunded by the time run() returns.
        self.shipment_service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(len(self.emitted["refunded"]), 1)
        outcome = self.emitted["refunded"][0]
        self.assertTrue(outcome.refunded)
        self.assertIn("printer offline", outcome.reason)

    def test_unexpected_print_error_still_refunds_but_is_labeled(self):
        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=ValueError("bad image"),
            ),
        ):
            self.worker.run()

        self.shipment_service.refund_shipment.assert_called_once_with("shp_123")
        outcome = self.emitted["refunded"][0]
        self.assertIn("Unexpected printing error", outcome.reason)

    def test_failed_refund_is_reported_rather_than_raised(self):
        self.shipment_service.refund_shipment.side_effect = RuntimeError("no network")

        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=RuntimeError("printer offline"),
            ),
        ):
            self.worker.run()

        outcome = self.emitted["refunded"][0]
        self.assertFalse(outcome.refunded)
        self.assertIn("no network", outcome.error)

    def test_failure_after_purchase_refunds_rather_than_reporting_an_error(self):
        """Postage bought then label download failed: money must come back."""
        with patch.object(
            self.worker.workflow,
            "prepare_label",
            side_effect=ShipmentPreparationError(
                "Label preparation failed: network blip", shipment=self.shipment
            ),
        ):
            self.worker.run()

        self.shipment_service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(len(self.emitted["refunded"]), 1)
        self.assertTrue(self.emitted["refunded"][0].refunded)
        # Must not claim nothing was bought - that would stop a manual refund.
        self.assertEqual(self.emitted["error"], [])

    def test_preparation_failure_reports_error_and_does_not_refund(self):
        with patch.object(
            self.worker.workflow,
            "prepare_label",
            side_effect=ShipmentPreparationError("EasyPost API error: nope"),
        ):
            self.worker.run()

        self.assertEqual(len(self.emitted["error"]), 1)
        self.assertIn("Shipment creation failed", self.emitted["error"][0])
        self.shipment_service.refund_shipment.assert_not_called()

    def test_dialog_mode_hands_the_label_off_without_printing(self):
        self.worker.use_dialog = True

        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch("shippy_gui.workers.shipment_worker.print_image") as mock_print,
        ):
            self.worker.run()

        mock_print.assert_not_called()
        self.assertEqual(len(self.emitted["label_ready"]), 1)
        self.shipment_service.refund_shipment.assert_not_called()

    def test_dialog_handoff_leaves_a_journal_record_to_recover_from(self):
        """The crash window: postage bought, dialog pending, app dies."""
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "pending.json")
        )
        self.worker.journal = journal
        self.worker.use_dialog = True

        with patch.object(
            self.worker.workflow, "prepare_label", side_effect=self._prepare_label_stub
        ):
            self.worker.run()

        # run() returned with the outcome unknown; the record must persist.
        self.assertEqual(
            [entry.shipment_id for entry in journal.pending()], ["shp_123"]
        )

    def test_successful_print_clears_the_journal(self):
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "pending.json")
        )
        self.worker.journal = journal

        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch("shippy_gui.workers.shipment_worker.print_image"),
        ):
            self.worker.run()

        self.assertEqual(journal.pending(), [])

    def test_successful_refund_clears_the_journal(self):
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "pending.json")
        )
        self.worker.journal = journal

        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=RuntimeError("printer offline"),
            ),
        ):
            self.worker.run()

        self.assertEqual(journal.pending(), [])

    def test_failed_refund_keeps_the_journal_record(self):
        """If the refund did not go through, the money is still outstanding."""
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "pending.json")
        )
        self.worker.journal = journal
        self.shipment_service.refund_shipment.side_effect = RuntimeError("no network")

        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=RuntimeError("printer offline"),
            ),
        ):
            self.worker.run()

        self.assertEqual(
            [entry.shipment_id for entry in journal.pending()], ["shp_123"]
        )

    def test_refund_policy_is_bound_to_the_buying_service(self):
        """A later service swap must not change who the refund goes through."""
        with (
            patch.object(
                self.worker.workflow,
                "prepare_label",
                side_effect=self._prepare_label_stub,
            ),
            patch(
                "shippy_gui.workers.shipment_worker.print_image",
                side_effect=RuntimeError("printer offline"),
            ),
        ):
            self.worker.run()

        self.shipment_service.refund_shipment.assert_called_once_with("shp_123")


if __name__ == "__main__":
    unittest.main()
