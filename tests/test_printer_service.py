"""Unit tests for typed printer service adaptation."""

import unittest

from shippy_gui.printing.printer_service import PrinterService


class FakePrinterBackend:
    """Simple backend stub for printer service tests."""

    def __init__(self, printers: list[str], default_printer: str | None):
        self._printers = printers
        self._default_printer = default_printer

    def get_available_printers(self) -> list[str]:
        return self._printers

    def get_default_printer(self) -> str | None:
        return self._default_printer

    def print_image(self, img, printer_name: str) -> None:
        raise NotImplementedError


class PrinterServiceTests(unittest.TestCase):
    """Tests for adapting raw backend printer names into PrinterInfo."""

    def test_get_available_printers_marks_default_and_usb_suffix(self):
        service = PrinterService(
            backend=FakePrinterBackend(
                printers=["iDPRT_SP310_20d1:7008", "Office Printer"],
                default_printer="iDPRT_SP310_20d1:7008",
            )
        )

        printers = service.get_available_printers()

        self.assertEqual(len(printers), 2)
        self.assertTrue(printers[0].is_default)
        self.assertEqual(printers[0].usb_id, "20D1:7008")
        self.assertEqual(printers[0].transport.value, "usb")
        self.assertFalse(printers[1].is_default)
        self.assertIsNone(printers[1].usb_id)
        self.assertIsNone(printers[1].transport)


if __name__ == "__main__":
    unittest.main()
