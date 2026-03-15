"""Unit tests for Windows printer filtering behavior."""

import sys
import types
import unittest
from unittest.mock import patch

from shippy_gui.printing.backends.windows import WindowsPrinterBackend


class FakePnPEntity:
    """Simple stand-in for WMI Win32_PnPEntity rows."""

    def __init__(
        self,
        device_id: str,
        pnp_class: str = "Printer",
        status: str = "OK",
        error_code: int = 0,
    ):
        self.DeviceID = device_id
        self.PNPClass = pnp_class
        self.Status = status
        self.ConfigManagerErrorCode = error_code


class FakeWMIConnection:
    """Test WMI connection that returns preconfigured entities."""

    def __init__(self, entities):
        self._entities = entities

    def Win32_PnPEntity(self):
        return self._entities


class WindowsPrinterBackendTests(unittest.TestCase):
    """Tests for Windows USB printer filtering helpers and behavior."""

    def setUp(self):
        self.backend = WindowsPrinterBackend()

    def test_extract_vid_pid(self):
        self.assertEqual(
            self.backend._extract_vid_pid(r"USB\VID_20D1&PID_7008\5&3A2D8B1E&0&1"),
            "20d1:7008",
        )

    def test_extract_vid_pid_returns_none_for_malformed_id(self):
        self.assertIsNone(self.backend._extract_vid_pid("USB\\MISSING"))

    def test_printer_name_matches_usb_id_with_supported_separators(self):
        self.assertTrue(
            self.backend._printer_name_matches_usb_id(
                "iDPRT_SP310_20d1:7008", "20d1:7008"
            )
        )
        self.assertTrue(
            self.backend._printer_name_matches_usb_id(
                "iDPRT SP310 20d1:7008", "20d1:7008"
            )
        )
        self.assertFalse(
            self.backend._printer_name_matches_usb_id(
                "iDPRT-SP310-20d1:7008", "20d1:7008"
            )
        )

    @patch.object(WindowsPrinterBackend, "_get_installed_printers")
    def test_get_available_printers_filters_to_matching_usb_suffixes(
        self, mock_get_installed_printers
    ):
        mock_get_installed_printers.return_value = [
            "iDPRT_SP310_20d1:7008",
            "Office Printer",
        ]
        fake_wmi_module = types.SimpleNamespace(
            WMI=lambda: FakeWMIConnection(
                [FakePnPEntity(r"USB\VID_20D1&PID_7008\5&3A2D8B1E&0&1")]
            )
        )

        with patch.dict(sys.modules, {"wmi": fake_wmi_module}):
            self.assertEqual(
                self.backend.get_available_printers(), ["iDPRT_SP310_20d1:7008"]
            )

    @patch.object(WindowsPrinterBackend, "_get_installed_printers")
    def test_get_available_printers_excludes_non_usb_and_disconnected_devices(
        self, mock_get_installed_printers
    ):
        mock_get_installed_printers.return_value = [
            "iDPRT_SP310_20d1:7008",
            "PDF Writer 1234:5678",
            "Network Printer 9999:0001",
        ]
        fake_wmi_module = types.SimpleNamespace(
            WMI=lambda: FakeWMIConnection(
                [
                    FakePnPEntity(r"SWD\PRINTENUM\PDF"),
                    FakePnPEntity(
                        r"USB\VID_9999&PID_0001\5&3A2D8B1E&0&1",
                        pnp_class="Printer",
                        status="Error",
                    ),
                ]
            )
        )

        with patch.dict(sys.modules, {"wmi": fake_wmi_module}):
            self.assertEqual(self.backend.get_available_printers(), [])

    def test_get_present_usb_printer_ids_excludes_config_manager_error_devices(self):
        fake_wmi_module = types.SimpleNamespace(
            WMI=lambda: FakeWMIConnection(
                [
                    FakePnPEntity(
                        r"USB\VID_20D1&PID_7008\5&3A2D8B1E&0&1",
                        error_code=45,
                    ),
                    FakePnPEntity(r"USB\VID_9999&PID_0001\5&3A2D8B1E&0&2"),
                ]
            )
        )

        with patch.dict(sys.modules, {"wmi": fake_wmi_module}):
            self.assertEqual(
                self.backend._get_present_usb_printer_ids(), {"9999:0001".upper()}
            )

    @patch.object(WindowsPrinterBackend, "_get_installed_printers")
    def test_get_available_printers_returns_empty_and_logs_warning_on_wmi_failure(
        self, mock_get_installed_printers
    ):
        mock_get_installed_printers.return_value = ["iDPRT_SP310_20d1:7008"]

        with patch.dict(sys.modules, {"wmi": None}):
            with self.assertLogs("shippy_gui.printing.backends.windows", "WARNING"):
                self.assertEqual(self.backend.get_available_printers(), [])


if __name__ == "__main__":
    unittest.main()
