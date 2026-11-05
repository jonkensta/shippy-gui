"""Tests for ShipmentWorker crash reporting."""

import unittest
from types import SimpleNamespace
from unittest import mock

from shippy_gui.core.ibp_server import IbpServerError
from shippy_gui.workers.shipment_worker import ShipmentWorker


class ShipmentWorkerCrashTests(unittest.TestCase):
    """An unexpected exception must reach the UI, never vanish with the thread."""

    def make_worker(self) -> ShipmentWorker:
        worker = ShipmentWorker(
            shipment_service=mock.Mock(),
            ibp_url="http://ibp.test/api",
            to_address=mock.Mock(),
            weight_lbs=1,
            printer_name="DYMO 0922:0028",
        )
        worker.workflow = mock.Mock()
        patcher = mock.patch(
            "shippy_gui.workers.shipment_worker.fetch_return_address",
            return_value=mock.sentinel.return_address,
        )
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)
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


class ShipmentWorkerReturnAddressTests(ShipmentWorkerCrashTests):
    """The return address is read from the IBP server before buying postage."""

    def test_server_return_address_is_the_from_address(self):
        worker = self.make_worker()
        worker.workflow.prepare_label.side_effect = ValueError("stop here")

        with self.assertLogs("shippy_gui.workers.shipment_worker", "ERROR"):
            worker.run()

        self.fetch.assert_called_once_with("http://ibp.test/api")
        workflow_input = worker.workflow.prepare_label.call_args.args[0]
        self.assertIs(workflow_input.from_address, mock.sentinel.return_address)

    def test_server_failure_buys_nothing(self):
        worker = self.make_worker()
        self.fetch.side_effect = IbpServerError("could not reach it")
        errors: list[str] = []
        worker.error.connect(errors.append)

        with self.assertLogs("shippy_gui.workers.shipment_worker", "ERROR"):
            worker.run()

        worker.workflow.prepare_label.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIn("could not reach it", errors[0])
        self.assertIn("No postage was bought", errors[0])


if __name__ == "__main__":
    unittest.main()
