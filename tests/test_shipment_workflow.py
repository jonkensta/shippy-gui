"""Unit tests for the headless shipment workflow service."""

import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.shipment_workflow import (
    ShipmentPreparationError,
    ShipmentWorkflow,
    ShipmentWorkflowInput,
)


class ShipmentWorkflowTests(unittest.TestCase):
    """Tests for shipment creation and label preparation."""

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

    def _workflow_input(self):
        return ShipmentWorkflowInput(
            from_address=self.from_address,
            to_address=self.to_address,
            weight_lbs=2,
        )

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_prepare_label_returns_shipment_and_image(self, mock_grab_png):
        from_addr = Mock(id="from_123")
        to_addr = Mock(id="to_123")
        shipment = Mock()
        shipment.postage_label.label_url = "https://example.com/label.png"

        self.service.create_address.side_effect = [from_addr, to_addr]
        self.service.buy_shipment.return_value = shipment
        mock_grab_png.return_value = Image.new("RGB", (10, 10), "white")
        progress = []
        warnings = []

        prepared = self.workflow.prepare_label(
            self._workflow_input(),
            on_progress=progress.append,
            on_warning=warnings.append,
        )

        self.assertEqual(prepared.shipment, shipment)
        self.assertIsNotNone(prepared.image)
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
            prepared = self.workflow.prepare_label(
                self._workflow_input(),
                on_warning=warnings.append,
            )

        self.assertEqual(prepared.shipment, shipment)
        self.assertEqual(len(warnings), 2)

    def test_failure_before_purchase_carries_no_shipment(self):
        self.service.create_address.side_effect = RuntimeError("network down")

        with self.assertRaises(ShipmentPreparationError) as caught:
            self.workflow.prepare_label(self._workflow_input())

        self.assertIn("network down", str(caught.exception))
        # No postage was bought, so there is nothing for the caller to refund.
        self.assertIsNone(caught.exception.shipment)

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_failure_after_purchase_carries_the_shipment(self, mock_grab_png):
        """Postage is bought before the label is fetched, so this costs money."""
        shipment = Mock(id="shp_PAID")
        shipment.postage_label.label_url = "https://example.com/label.png"
        self.service.create_address.side_effect = [Mock(id="f"), Mock(id="t")]
        self.service.buy_shipment.return_value = shipment
        mock_grab_png.side_effect = OSError("network blip")

        with self.assertRaises(ShipmentPreparationError) as caught:
            self.workflow.prepare_label(self._workflow_input())

        self.assertIs(caught.exception.shipment, shipment)
        self.assertIn("Label preparation failed", str(caught.exception))

    def test_failure_stamping_the_logo_still_carries_the_shipment(self):
        shipment = Mock(id="shp_PAID")
        shipment.postage_label.label_url = "https://example.com/label.png"
        self.service.create_address.side_effect = [Mock(id="f"), Mock(id="t")]
        self.service.buy_shipment.return_value = shipment

        with tempfile.NamedTemporaryFile(suffix=".jpg") as broken_logo:
            broken_logo.write(b"not an image")
            broken_logo.flush()
            workflow_input = ShipmentWorkflowInput(
                from_address=self.from_address,
                to_address=self.to_address,
                weight_lbs=2,
                logo_path=broken_logo.name,
            )
            with (
                patch(
                    "shippy_gui.core.shipment_workflow.grab_png_from_url",
                    return_value=Image.new("RGB", (10, 10), "white"),
                ),
                self.assertRaises(ShipmentPreparationError) as caught,
            ):
                self.workflow.prepare_label(workflow_input)

        self.assertIs(caught.exception.shipment, shipment)

    def test_core_workflow_does_not_import_qt(self):
        """core must stay headless: importing it must not pull in PySide6."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import shippy_gui.core.shipment_workflow; "
                "sys.exit(1 if any(m.startswith('PySide6') for m in sys.modules) else 0)",
            ],
            check=False,
            capture_output=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"core.shipment_workflow pulled in PySide6: {result.stderr.decode()}",
        )


if __name__ == "__main__":
    unittest.main()
