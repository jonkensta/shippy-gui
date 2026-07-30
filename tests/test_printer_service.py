"""Unit tests for typed printer service adaptation."""

import unittest

from shippy_gui.printing.backends.windows import WindowsPrinterBackend
from shippy_gui.printing.printer_service import PrinterService


class FakePrinterBackend:
    """Simple backend stub for printer service tests.

    Name parsing is delegated to the real Windows backend, because the service
    is meant to report whatever identifier the backend matched on rather than
    deriving one of its own.
    """

    def __init__(self, printers: list[str], default_printer: str | None):
        self._printers = printers
        self._default_printer = default_printer

    def get_available_printers(self) -> list[str]:
        return self._printers

    def get_default_printer(self) -> str | None:
        return self._default_printer

    def print_image(self, img, printer_name: str) -> None:
        raise NotImplementedError

    @staticmethod
    def parse_name_identifier(printer_name: str):
        return WindowsPrinterBackend.parse_name_identifier(printer_name)


class NamelessPrinterBackend(FakePrinterBackend):
    """Backend for a platform with no USB naming convention."""

    @staticmethod
    def parse_name_identifier(printer_name: str):
        return None, None


class PrinterServiceTests(unittest.TestCase):
    """Tests for adapting raw backend printer names into PrinterInfo."""

    def test_get_available_printers_marks_default_and_usb_suffix(self):
        service = PrinterService(
            backend=FakePrinterBackend(
                printers=["iDPRT_SP310_20d1:7008", "Office"],
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

    def test_serial_named_printer_is_reported_as_usb(self):
        service = PrinterService(
            backend=FakePrinterBackend(
                printers=["Front-Desk PM-2411-BT Q529E65K5250028"],
                default_printer=None,
            )
        )

        printer = service.get_available_printers()[0]

        self.assertEqual(printer.serial, "Q529E65K5250028")
        self.assertIsNone(printer.usb_id)
        self.assertEqual(printer.transport.value, "usb")

    def test_a_name_without_an_identifier_reports_no_transport(self):
        service = PrinterService(
            backend=FakePrinterBackend(printers=["Office"], default_printer=None)
        )

        printer = service.get_available_printers()[0]

        self.assertIsNone(printer.serial)
        self.assertIsNone(printer.usb_id)
        self.assertIsNone(printer.transport)

    def test_two_same_model_units_are_distinguishable_by_serial(self):
        service = PrinterService(
            backend=FakePrinterBackend(
                printers=[
                    "Front-Desk PM-2411-BT Q529E65K5250028",
                    "Back-Room PM-2411-BT Q529E65K5250099",
                ],
                default_printer=None,
            )
        )

        serials = {printer.serial for printer in service.get_available_printers()}

        self.assertEqual(serials, {"Q529E65K5250028", "Q529E65K5250099"})

    def test_a_backend_with_no_naming_convention_reports_no_transport(self):
        """The service must not invent a USB identity the backend never matched."""
        service = PrinterService(
            backend=NamelessPrinterBackend(
                printers=["Brother_HL2350DW"], default_printer=None
            )
        )

        printer = service.get_available_printers()[0]

        self.assertIsNone(printer.transport)
        self.assertIsNone(printer.usb_id)
        self.assertIsNone(printer.serial)


if __name__ == "__main__":
    unittest.main()
