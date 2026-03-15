"""Unit tests for the pure shipment workflow service."""

import unittest
from unittest.mock import Mock, patch

from PIL import Image

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.shipment_workflow import (
    ShipmentWorkflowInput,
    ShipmentWorkflow,
    ShipmentWorkflowStatus,
)


class ShipmentWorkflowTests(unittest.TestCase):
    """Tests for shipment workflow preparation and print/refund behavior."""

    def setUp(self):
        self.service = Mock()
        self.workflow = ShipmentWorkflow(self.service)
        self.from_address = ReturnAddressConfig(
            name="Inside Books Project",
            street1="PO Box 1",
            city="Austin",
            state="TX",
            zipcode="78703",
        )
        self.to_address = RecipientAddress(
            name="Jane Doe",
            street1="123 Prison Rd",
            city="Huntsville",
            state="TX",
            zipcode="77340",
        )

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_prepare_label_returns_ready_result(self, mock_grab_png):
        from_addr = Mock(id="from_123")
        to_addr = Mock(id="to_123")
        shipment = Mock()
        shipment.postage_label.label_url = "https://example.com/label.png"

        self.service.create_address.side_effect = [from_addr, to_addr]
        self.service.buy_shipment.return_value = shipment
        mock_grab_png.return_value = Image.new("RGB", (10, 10), "white")
        progress = []
        warnings = []

        result = self.workflow.prepare_label(
            ShipmentWorkflowInput(
                from_address=self.from_address,
                to_address=self.to_address,
                weight_lbs=2,
            ),
            on_progress=progress.append,
            on_warning=warnings.append,
        )

        self.assertEqual(result.status, ShipmentWorkflowStatus.READY)
        self.assertEqual(result.shipment, shipment)
        self.assertIsNotNone(result.image)
        self.assertIn("Purchasing postage...", progress)
        self.assertEqual(warnings, [])

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_prepare_label_emits_warnings_for_verify_failures(self, mock_grab_png):
        from_addr = Mock(id="from_123")
        to_addr = Mock(id="to_123")
        shipment = Mock()
        shipment.postage_label.label_url = "https://example.com/label.png"

        self.service.create_address.side_effect = [from_addr, to_addr]
        self.service.verify_address.side_effect = [Exception("bad"), Exception("bad")]
        self.service.buy_shipment.return_value = shipment
        mock_grab_png.return_value = Image.new("RGB", (10, 10), "white")

        warnings = []
        # Match the production error type contract closely enough for the warning branch.
        with patch(
            "shippy_gui.core.shipment_workflow.easypost.errors.InvalidRequestError",
            Exception,
        ):
            result = self.workflow.prepare_label(
                ShipmentWorkflowInput(
                    from_address=self.from_address,
                    to_address=self.to_address,
                    weight_lbs=2,
                ),
                on_warning=warnings.append,
            )

        self.assertEqual(result.status, ShipmentWorkflowStatus.READY)
        self.assertEqual(len(warnings), 2)

    def test_print_prepared_label_requests_refund_on_runtime_error(self):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        prepared_result = Mock(
            status=ShipmentWorkflowStatus.READY,
            shipment=shipment,
            image=Image.new("RGB", (10, 10), "white"),
        )

        with patch(
            "shippy_gui.core.shipment_workflow.print_image",
            side_effect=RuntimeError("printer offline"),
        ):
            result = self.workflow.print_prepared_label(prepared_result, "Printer Name")

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertTrue(result.refund_requested)
        self.service.refund_shipment.assert_called_once_with("shp_123")

    def test_refund_after_failure_reports_secondary_refund_error(self):
        shipment = Mock(id="shp_123")
        self.service.refund_shipment.side_effect = RuntimeError("refund failed")

        result = self.workflow.refund_after_failure(shipment, "Printing error")

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertFalse(result.refund_requested)
        self.assertIn("Refund also failed", result.message)


if __name__ == "__main__":
    unittest.main()
