"""Tests for ShipmentWorker crash reporting."""

import unittest
from types import SimpleNamespace
from unittest import mock

from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShipmentWorkerCrashTests(unittest.TestCase):
    """An unexpected exception must reach the UI, never vanish with the thread."""

    def make_worker(self) -> ShipmentWorker:
        worker = ShipmentWorker(
            shipment_service=mock.Mock(),
            from_address=mock.Mock(),
            to_address=mock.Mock(),
            weight_lbs=1,
            printer_name="DYMO 0922:0028",
        )
        worker.workflow = mock.Mock()
        return worker

    def test_crash_before_purchase_emits_error(self):
        worker = self.make_worker()
        worker.workflow.prepare_label.side_effect = ValueError("boom")
        errors: list[str] = []
        worker.error.connect(errors.append)

        with self.assertLogs("shippy_gui.workers.shipment_worker", "ERROR"):
            worker.run()

        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])

    def test_crash_after_purchase_names_shipment_and_does_not_refund(self):
        worker = self.make_worker()
        shipment = SimpleNamespace(tracking_code="9400TEST", id="shp_1")
        worker.workflow.prepare_label.return_value = SimpleNamespace(
            status=None, shipment=shipment, image=object(), message=""
        )
        worker.workflow.print_prepared_label.side_effect = RuntimeError("late")
        errors: list[str] = []
        worker.error.connect(errors.append)

        with self.assertLogs("shippy_gui.workers.shipment_worker", "ERROR"):
            worker.run()

        self.assertEqual(len(errors), 1)
        self.assertIn("9400TEST", errors[0])
        worker.workflow.refund_after_failure.assert_not_called()


if __name__ == "__main__":
    unittest.main()
