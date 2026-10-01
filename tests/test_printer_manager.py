"""Adapter tests for shippy-gui printing over ibp-printing.

Discovery rules and platform backends are tested in ibp-printing itself; these
tests only check how shippy-gui maps them, using a fake backend.
"""

import unittest
from typing import Optional
from unittest.mock import Mock, patch

import ibp_printing
from ibp_printing import (
    Discovery,
    JobOutcome,
    PrinterBackend,
    PrinterCandidate,
    PrintError,
    PrintQueue,
    PrintResult,
    UsbDevice,
)
from PIL import Image
from PySide6.QtCore import QRectF  # pylint: disable=no-name-in-module

from shippy_gui.core.constants import PRINT_TRACK_TIMEOUT_S
from shippy_gui.printing import printer_manager
from shippy_gui.printing.models import PrinterTransport


def _usb_candidate(name: str, vid_pid: str, **queue_kwargs) -> PrinterCandidate:
    device = UsbDevice(
        device_id=f"USB\\VID_{vid_pid[:4]}&PID_{vid_pid[5:]}\\1", vid_pid=vid_pid
    )
    return PrinterCandidate(PrintQueue(name=name, **queue_kwargs), vid_pid, (device,))


class FakeBackend(PrinterBackend):
    """In-memory backend recording print calls."""

    platform_name = "fake"

    def __init__(self, candidates=(), default=None, fail_with=None, outcome=None):
        self.candidates = list(candidates)
        self.default = default
        self.fail_with = fail_with
        self.outcome = outcome or JobOutcome.NOT_TRACKED
        self.printed: list[tuple[str, str, float]] = []

    def discover(self) -> Discovery:
        return Discovery(candidates=self.candidates)

    def get_default_printer(self) -> Optional[str]:
        return self.default

    def print_image(
        self,
        img: Image.Image,
        printer_name: str,
        *,
        job_name: str,
        track_timeout_s: float = 0.0,
    ) -> PrintResult:
        if self.fail_with is not None:
            raise self.fail_with
        self.printed.append((printer_name, job_name, track_timeout_s))
        return PrintResult(printer_name, job_name, outcome=self.outcome)


class PrinterManagerTests(unittest.TestCase):
    """Tests for the shippy-gui printing adapter."""

    def setUp(self):
        self.backend = FakeBackend()
        ibp_printing.set_backend(self.backend)
        self.addCleanup(ibp_printing.set_backend, None)

    def test_get_available_printers_maps_usable_candidates_best_first(self):
        self.backend.candidates = [
            _usb_candidate("Zebra 20d1:7008", "20D1:7008"),
            _usb_candidate("Alpha-0922:0028", "0922:0028", is_default=True),
            PrinterCandidate(PrintQueue(name="Office Laser"), None),
            PrinterCandidate(PrintQueue(name="Unplugged 1111:2222"), "1111:2222"),
        ]

        printers = printer_manager.get_available_printers()

        self.assertEqual(
            [printer.system_name for printer in printers],
            ["Alpha-0922:0028", "Zebra 20d1:7008"],
        )
        self.assertTrue(printers[0].is_default)
        self.assertEqual(printers[0].usb_id, "0922:0028")
        self.assertEqual(printers[0].transport, PrinterTransport.USB)
        self.assertFalse(printers[1].is_default)

    def test_get_available_printers_lists_non_usb_queues_without_usb_matching(self):
        self.backend.candidates = [
            PrinterCandidate(PrintQueue(name="cups-queue"), None, usb_matching=False)
        ]

        printers = printer_manager.get_available_printers()

        self.assertEqual(len(printers), 1)
        self.assertIsNone(printers[0].usb_id)
        self.assertIsNone(printers[0].transport)

    def test_get_available_printers_returns_empty_on_discovery_error(self):
        def broken_discover():
            raise OSError("spooler down")

        self.backend.discover = broken_discover  # type: ignore[method-assign]

        with self.assertLogs("shippy_gui.printing.printer_manager", "ERROR"):
            self.assertEqual(printer_manager.get_available_printers(), [])

    def test_get_default_printer_delegates_to_backend(self):
        self.backend.default = "Alpha 0922:0028"
        self.assertEqual(printer_manager.get_default_printer(), "Alpha 0922:0028")

    def test_print_image_passes_job_name_and_track_timeout(self):
        printer_manager.print_image(
            Image.new("RGB", (4, 6)), "Alpha 0922:0028", job_name="Label 9400"
        )

        self.assertEqual(len(self.backend.printed), 1)
        printer_name, job_name, timeout = self.backend.printed[0]
        self.assertEqual(printer_name, "Alpha 0922:0028")
        self.assertTrue(job_name.startswith("Label 9400"))
        self.assertEqual(timeout, PRINT_TRACK_TIMEOUT_S)

    def test_print_image_logs_but_does_not_raise_on_bad_job_outcome(self):
        self.backend.outcome = JobOutcome.ERROR

        with (
            self.assertLogs("ibp_printing", "ERROR"),
            self.assertLogs("shippy_gui.printing.printer_manager", "WARNING"),
        ):
            result = printer_manager.print_image(Image.new("RGB", (4, 6)), "Alpha")

        self.assertEqual(result.outcome, JobOutcome.ERROR)

    def test_print_image_raises_runtime_error_when_spooling_fails(self):
        self.backend.fail_with = PrintError("CreateDC failed")

        with self.assertRaises(RuntimeError), self.assertLogs("ibp_printing", "ERROR"):
            printer_manager.print_image(Image.new("RGB", (4, 6)), "Alpha")


class DialogPrintTests(unittest.TestCase):
    """_print_with_qprinter separates 'nothing sent' from 'may have printed'."""

    def _run(self, painter: Mock, image_qt_error: Optional[Exception] = None):
        printer = Mock()
        printer.pageRect.return_value = QRectF(0, 0, 400, 600)
        patches = [patch.object(printer_manager, "QPainter", return_value=painter)]
        if image_qt_error is not None:
            patches.append(
                patch.object(
                    printer_manager.ImageQt, "ImageQt", side_effect=image_qt_error
                )
            )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return printer_manager._print_with_qprinter(  # pylint: disable=protected-access
            Image.new("RGB", (40, 60), "white"), printer
        )

    @staticmethod
    def _painter(begin=True, end=True, draw_error=None) -> Mock:
        painter = Mock()
        painter.begin.return_value = begin
        painter.end.return_value = end
        if draw_error is not None:
            painter.drawImage.side_effect = draw_error
        return painter

    def test_printed(self):
        painter = self._painter()
        self.assertEqual(self._run(painter), printer_manager.DialogPrintStatus.PRINTED)
        painter.end.assert_called_once_with()

    def test_begin_failure_is_not_sent(self):
        painter = self._painter(begin=False)
        with self.assertLogs("shippy_gui.printing.printer_manager", "WARNING"):
            status = self._run(painter)
        self.assertEqual(status, printer_manager.DialogPrintStatus.NOT_SENT)
        painter.drawImage.assert_not_called()

    def test_failure_before_begin_is_not_sent(self):
        painter = self._painter()
        with self.assertLogs("shippy_gui.printing.printer_manager", "ERROR"):
            status = self._run(painter, image_qt_error=ValueError("bad image"))
        self.assertEqual(status, printer_manager.DialogPrintStatus.NOT_SENT)
        painter.begin.assert_not_called()

    def test_failure_after_begin_is_uncertain(self):
        painter = self._painter(draw_error=RuntimeError("draw failed"))
        with self.assertLogs("shippy_gui.printing.printer_manager", "ERROR"):
            status = self._run(painter)
        self.assertEqual(status, printer_manager.DialogPrintStatus.UNCERTAIN)
        painter.end.assert_called_once_with()

    def test_end_failure_is_uncertain(self):
        painter = self._painter(end=False)
        with self.assertLogs("shippy_gui.printing.printer_manager", "WARNING"):
            status = self._run(painter)
        self.assertEqual(status, printer_manager.DialogPrintStatus.UNCERTAIN)

    def test_statuses_compare_to_legacy_strings(self):
        self.assertEqual(printer_manager.DialogPrintStatus.PRINTED, "printed")
        self.assertEqual(printer_manager.DialogPrintStatus.CANCELED, "canceled")


if __name__ == "__main__":
    unittest.main()
