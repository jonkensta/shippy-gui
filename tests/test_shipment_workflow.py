"""Unit tests for the pure shipment workflow service."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import ibp_printing
from ibp_printing.labels import set_journal_path
from PIL import Image

from journal_fakes import install_fake_journal

from shippy_gui.core import label_journal
from shippy_gui.core.models import RecipientAddress, ReturnAddressConfig
from shippy_gui.core.shipment_workflow import (
    ShipmentWorkflowInput,
    ShipmentWorkflow,
    ShipmentWorkflowStatus,
)


class ShipmentWorkflowTests(unittest.TestCase):
    """Tests for shipment workflow preparation and print/refund behavior."""

    def setUp(self):
        self.journal = install_fake_journal(self)
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
    def test_prepare_label_records_purchase_in_journal(self, mock_grab_png):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        shipment.postage_label.label_url = "https://example.com/label.png"
        self.service.create_address.side_effect = [Mock(id="f"), Mock(id="t")]
        self.service.buy_shipment.return_value = shipment
        mock_grab_png.return_value = Image.new("RGB", (10, 10), "white")

        result = self.workflow.prepare_label(
            ShipmentWorkflowInput(
                from_address=self.from_address,
                to_address=self.to_address,
                weight_lbs=2,
            )
        )

        self.assertEqual(
            self.journal.purchases,
            [
                {
                    "recipient_key": "jane doe|123 prison rd|huntsville|tx|77340",
                    "recipient_label": "Jane Doe, 123 Prison Rd, Huntsville, TX",
                    "tracking_code": "TRACK123",
                    "shipment_id": "shp_123",
                    "app": "shippy-gui",
                }
            ],
        )
        self.assertEqual(
            result.identity.recipient_label, "Jane Doe, 123 Prison Rd, Huntsville, TX"
        )
        self.assertIsNotNone(result.label_record)

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

    def test_print_prepared_label_treats_unexpected_errors_as_uncertain(self):
        # R3: anything other than PrintError may have happened after the job
        # reached the spooler, so no refund and no save-for-retry.
        for error in (
            RuntimeError("printer offline"),
            OSError("temp file could not be deleted"),
            ValueError("bad state"),
        ):
            with self.subTest(error=type(error).__name__):
                self.service.reset_mock()
                with (
                    patch(
                        "shippy_gui.core.shipment_workflow.print_image",
                        side_effect=error,
                    ),
                    patch(
                        "shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry"
                    ) as mock_save,
                    self.assertLogs("shippy_gui.core.shipment_workflow", "ERROR"),
                ):
                    result = self.workflow.print_prepared_label(
                        self._prepared(), "Printer Name"
                    )

                self.assertEqual(result.status, ShipmentWorkflowStatus.SUCCESS)
                self.assertFalse(result.refund_requested)
                self.service.refund_shipment.assert_not_called()
                mock_save.assert_not_called()
                self.assertIsNone(result.saved_label_path)
                self.assertIsNotNone(result.print_warning)
                self.assertIn(str(error), result.print_warning)
                self.assertIn("may or may NOT have printed", result.message)
                self.assertIn("NOT refunded", result.message)
                self.assertIn("TRACK123", result.message)
                self.assertEqual(self.journal.statuses()[-1], "check_printer")

    def _prepared(self):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        return Mock(
            status=ShipmentWorkflowStatus.READY,
            shipment=shipment,
            image=Image.new("RGB", (10, 10), "white"),
            identity=label_journal.LabelIdentity("key", "Jane Doe, Huntsville"),
            label_record=None,
        )

    def _failing_backend(self):
        backend = Mock(spec=ibp_printing.PrinterBackend)
        backend.print_image.side_effect = ibp_printing.PrintError("CreateDC failed")
        ibp_printing.set_backend(backend)
        self.addCleanup(ibp_printing.set_backend, None)
        return backend

    def test_print_prepared_label_saves_label_without_refund_on_print_error(self):
        prepared_result = self._prepared()
        backend = self._failing_backend()
        watch_dir = Path(self.enterContext(tempfile.TemporaryDirectory()))
        # The real save_for_retry also journals the label: keep it out of the
        # developer's real label journal.
        set_journal_path(watch_dir / "labels.jsonl")
        self.addCleanup(set_journal_path, None)
        real_save = ibp_printing.save_for_retry

        def save_into_temp(img, name, meta=None):
            return real_save(img, name, watch_dir=watch_dir, meta=meta)

        with (
            patch(
                "shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry",
                side_effect=save_into_temp,
            ) as mock_save,
            self.assertLogs("ibp_printing", "ERROR"),
        ):
            result = self.workflow.print_prepared_label(prepared_result, "Printer Name")

        self.assertEqual(result.status, ShipmentWorkflowStatus.SUCCESS)
        self.assertFalse(result.refund_requested)
        self.service.refund_shipment.assert_not_called()
        mock_save.assert_called_once_with(
            prepared_result.image, name="TRACK123", meta=ANY
        )
        meta = mock_save.call_args.kwargs["meta"]
        self.assertEqual(meta["tracking_code"], "TRACK123")
        self.assertEqual(meta["shipment_id"], "shp_123")
        self.assertEqual(meta["app"], "shippy-gui")
        self.assertEqual(meta["recipient_label"], "Jane Doe, Huntsville")
        self.assertEqual(meta["recipient_key"], "key")
        self.assertIn("created", meta)
        self.assertEqual(
            self.journal.status_updates,
            [("TRACK123", "queued", str(result.saved_label_path))],
        )
        self.assertIsNotNone(result.saved_label_path)
        self.assertTrue(result.saved_label_path.exists())
        self.assertEqual(result.saved_label_path.parent, watch_dir / "to-print")
        self.assertIn("TRACK123", result.saved_label_path.name)
        self.assertIn("did NOT print", result.message)
        self.assertIn("CreateDC failed", result.message)
        self.assertIn(str(result.saved_label_path), result.message)
        self.assertIn("label watcher", result.message)
        self.assertIn("NOT refunded", result.message)
        self.assertIn("TRACK123", result.message)
        # R5: tell the volunteer to remove the queued file before printing it
        # by hand or refunding, so the watcher does not print it too.
        self.assertIn("DELETE it from", result.message)
        self.assertIn(str(watch_dir / "to-print"), result.message)
        self.assertIn("TRACK123", backend.print_image.call_args.kwargs["job_name"])

    def test_print_prepared_label_refunds_when_label_cannot_be_saved(self):
        prepared_result = self._prepared()
        self._failing_backend()

        with (
            patch(
                "shippy_gui.core.shipment_workflow.ibp_printing.save_for_retry",
                side_effect=OSError("disk full"),
            ),
            self.assertLogs("ibp_printing", "ERROR"),
            self.assertLogs("shippy_gui.core.shipment_workflow", "ERROR"),
        ):
            result = self.workflow.print_prepared_label(prepared_result, "Printer Name")

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertTrue(result.refund_requested)
        self.assertIsNone(result.saved_label_path)
        self.assertIn("CreateDC failed", result.message)
        self.assertIn("disk full", result.message)
        self.assertIn("Refund requested", result.message)
        self.service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(self.journal.statuses(), ["refunded"])

    def _prepare_after_purchase(self, *, logo_path=None):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        shipment.postage_label.label_url = "https://example.com/label.png"
        self.service.create_address.side_effect = [Mock(id="f"), Mock(id="t")]
        self.service.buy_shipment.return_value = shipment
        with self.assertLogs("shippy_gui.core.shipment_workflow", "ERROR"):
            return self.workflow.prepare_label(
                ShipmentWorkflowInput(
                    from_address=self.from_address,
                    to_address=self.to_address,
                    weight_lbs=2,
                    logo_path=logo_path,
                )
            )

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_prepare_label_refunds_when_label_download_fails(self, mock_grab_png):
        mock_grab_png.side_effect = ConnectionError("download failed")

        result = self._prepare_after_purchase()

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertTrue(result.refund_requested)
        self.assertIn("download failed", result.message)
        self.service.refund_shipment.assert_called_once_with("shp_123")
        self.assertEqual(len(self.journal.purchases), 1)
        self.assertEqual(self.journal.statuses(), ["refunded"])

    @patch("shippy_gui.core.shipment_workflow.grab_png_from_url")
    def test_prepare_label_refunds_when_logo_cannot_be_applied(self, mock_grab_png):
        mock_grab_png.return_value = Image.new("RGB", (10, 10), "white")
        logo = self.enterContext(tempfile.NamedTemporaryFile(suffix=".jpg"))
        logo.write(b"not an image")
        logo.flush()

        result = self._prepare_after_purchase(logo_path=logo.name)

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertTrue(result.refund_requested)
        self.service.refund_shipment.assert_called_once_with("shp_123")

    def test_prepare_label_does_not_refund_when_purchase_fails(self):
        self.service.create_address.side_effect = [Mock(id="f"), Mock(id="t")]
        self.service.buy_shipment.side_effect = RuntimeError("no rates")

        result = self.workflow.prepare_label(
            ShipmentWorkflowInput(
                from_address=self.from_address,
                to_address=self.to_address,
                weight_lbs=2,
            )
        )

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertIn("no rates", result.message)
        self.service.refund_shipment.assert_not_called()
        self.assertEqual(self.journal.purchases, [])

    def test_print_prepared_label_warns_without_refund_on_bad_job_outcome(self):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        prepared_result = Mock(
            status=ShipmentWorkflowStatus.READY,
            shipment=shipment,
            image=Image.new("RGB", (10, 10), "white"),
        )
        print_result = ibp_printing.PrintResult(
            "Alpha 20d1:7008", "Shipping Label", outcome=ibp_printing.JobOutcome.ERROR
        )

        with patch(
            "shippy_gui.core.shipment_workflow.print_image", return_value=print_result
        ):
            result = self.workflow.print_prepared_label(
                prepared_result, "Alpha 20d1:7008"
            )

        self.assertEqual(result.status, ShipmentWorkflowStatus.SUCCESS)
        self.assertFalse(result.refund_requested)
        self.service.refund_shipment.assert_not_called()
        self.assertIsNotNone(result.print_warning)
        self.assertIn("may NOT have printed", result.message)
        self.assertIn("'error'", result.message)
        self.assertIn("Alpha 20d1:7008", result.message)
        self.assertIn("TRACK123", result.message)
        self.assertIn(str(ibp_printing.default_log_dir()), result.message)
        self.assertEqual(self.journal.statuses(), ["check_printer"])

    def test_print_prepared_label_warns_without_refund_on_uncertain_outcomes(self):
        for outcome in (
            ibp_printing.JobOutcome.UNCERTAIN,
            ibp_printing.JobOutcome.TRACKING_FAILED,
        ):
            with self.subTest(outcome=outcome):
                self.service.reset_mock()
                print_result = ibp_printing.PrintResult(
                    "Alpha", "Shipping Label", outcome=outcome
                )
                with patch(
                    "shippy_gui.core.shipment_workflow.print_image",
                    return_value=print_result,
                ):
                    result = self.workflow.print_prepared_label(
                        self._prepared(), "Alpha"
                    )

                self.assertEqual(result.status, ShipmentWorkflowStatus.SUCCESS)
                self.service.refund_shipment.assert_not_called()
                self.assertIsNone(result.saved_label_path)
                self.assertIsNotNone(result.print_warning)
                self.assertIn("may NOT have printed", result.message)
                self.assertIn("check the printer before reprinting", result.message)
                self.assertEqual(self.journal.statuses()[-1], "check_printer")

    def test_print_prepared_label_succeeds_without_warning_on_ok_outcome(self):
        shipment = Mock(id="shp_123")
        shipment.tracking_code = "TRACK123"
        prepared_result = Mock(
            status=ShipmentWorkflowStatus.READY,
            shipment=shipment,
            image=Image.new("RGB", (10, 10), "white"),
        )
        print_result = ibp_printing.PrintResult(
            "Alpha", "Shipping Label", outcome=ibp_printing.JobOutcome.COMPLETED
        )

        with patch(
            "shippy_gui.core.shipment_workflow.print_image", return_value=print_result
        ):
            result = self.workflow.print_prepared_label(prepared_result, "Alpha")

        self.assertEqual(result.status, ShipmentWorkflowStatus.SUCCESS)
        self.assertIsNone(result.print_warning)
        self.assertIn("Label printed successfully", result.message)
        self.assertEqual(self.journal.status_updates, [("TRACK123", "printed", None)])

    def test_refund_after_failure_reports_secondary_refund_error(self):
        shipment = Mock(id="shp_123")
        self.service.refund_shipment.side_effect = RuntimeError("refund failed")

        result = self.workflow.refund_after_failure(shipment, "Printing error")

        self.assertEqual(result.status, ShipmentWorkflowStatus.ERROR)
        self.assertFalse(result.refund_requested)
        self.assertIn("Refund also failed", result.message)


if __name__ == "__main__":
    unittest.main()
