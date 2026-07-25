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

    def test_parse_name_identifier_reads_vid_pid_with_supported_separators(self):
        for name in (
            "iDPRT_SP310_20d1:7008",
            "iDPRT SP310 20d1:7008",
            "iDPRT-SP310-20d1:7008",
        ):
            self.assertEqual(
                WindowsPrinterBackend.parse_name_identifier(name),
                ("20D1:7008", None),
                msg=name,
            )

    def test_parse_name_identifier_reads_a_serial_suffix(self):
        self.assertEqual(
            WindowsPrinterBackend.parse_name_identifier(
                "Front-Desk PM-2411-BT Q529E65K5250028"
            ),
            (None, "Q529E65K5250028"),
        )

    def test_parse_name_identifier_prefers_vid_pid_over_serial(self):
        """VID:PID is the older spelling and stays authoritative when present."""
        self.assertEqual(
            WindowsPrinterBackend.parse_name_identifier("PM2411 Q529E65 20d1:7008"),
            ("20D1:7008", None),
        )

    def test_parse_name_identifier_ignores_names_without_an_identifier(self):
        self.assertEqual(
            WindowsPrinterBackend.parse_name_identifier("Office"), (None, None)
        )

    def test_serial_named_queues_bind_only_to_their_own_unit(self):
        """Two printers of one model share a VID:PID; only serials separate them."""
        device_ids = {
            r"USB\VID_2E3C&PID_5760\Q529E65K5250028",
            r"USB\VID_2E3C&PID_5760\Q529E65K5250099",
        }

        first = WindowsPrinterBackend.matching_device_keys(
            "Front-Desk PM-2411-BT Q529E65K5250028", device_ids
        )
        second = WindowsPrinterBackend.matching_device_keys(
            "Back-Room PM-2411-BT Q529E65K5250099", device_ids
        )

        self.assertEqual(first, {("2E3C", "5760", "Q529E65K5250028")})
        self.assertEqual(second, {("2E3C", "5760", "Q529E65K5250099")})
        self.assertNotEqual(first, second)

    def test_serial_match_requires_the_whole_instance_tail(self):
        """A suffix-colliding serial must not bind to another unit."""
        device_ids = {r"USB\VID_2E3C&PID_5760\XXQ529E65K5250028"}

        keys = WindowsPrinterBackend.matching_device_keys(
            "Front-Desk PM-2411-BT Q529E65K5250028", device_ids
        )

        self.assertEqual(keys, set())

    def test_serial_match_tolerates_a_revision_segment(self):
        device_ids = {r"USB\VID_2E3C&PID_5760&REV_0100\Q529E65K5250028"}

        keys = WindowsPrinterBackend.matching_device_keys(
            "Front-Desk PM-2411-BT Q529E65K5250028", device_ids
        )

        self.assertEqual(keys, {("2E3C", "5760", "Q529E65K5250028")})

    def test_vid_pid_queue_counts_a_printer_once_despite_child_nodes(self):
        """Interface nodes must not make one printer look like several."""
        device_ids = {
            r"USB\VID_20D1&PID_7008\5&3A2D8B1E&0&1",
            r"USB\VID_20D1&PID_7008&MI_00\6&1F2E3D4C&0&0000",
        }

        keys = WindowsPrinterBackend.matching_device_keys(
            "iDPRT_SP310_20d1:7008", device_ids
        )

        self.assertEqual(keys, {("20D1", "7008", "5&3A2D8B1E&0&1")})

    def test_vid_pid_queue_does_not_match_a_different_model(self):
        device_ids = {r"USB\VID_9999&PID_0001\5&3A2D8B1E&0&1"}

        self.assertEqual(
            WindowsPrinterBackend.matching_device_keys(
                "iDPRT_SP310_20d1:7008", device_ids
            ),
            set(),
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

    def test_get_present_usb_device_ids_excludes_config_manager_error_devices(self):
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
                self.backend._get_present_usb_device_ids(),
                {r"USB\VID_9999&PID_0001\5&3A2D8B1E&0&2"},
            )

    @patch.object(WindowsPrinterBackend, "_get_installed_printers")
    def test_get_available_printers_lists_two_same_model_units_by_serial(
        self, mock_get_installed_printers
    ):
        """The point of the change: same model, two units, both selectable."""
        mock_get_installed_printers.return_value = [
            "Front-Desk PM-2411-BT Q529E65K5250028",
            "Back-Room PM-2411-BT Q529E65K5250099",
            "Unplugged PM-2411-BT Q529E65K5250777",
        ]
        fake_wmi_module = types.SimpleNamespace(
            WMI=lambda: FakeWMIConnection(
                [
                    FakePnPEntity(r"USB\VID_2E3C&PID_5760\Q529E65K5250028"),
                    FakePnPEntity(r"USB\VID_2E3C&PID_5760\Q529E65K5250099"),
                ]
            )
        )

        with patch.dict(sys.modules, {"wmi": fake_wmi_module}):
            self.assertEqual(
                self.backend.get_available_printers(),
                [
                    "Front-Desk PM-2411-BT Q529E65K5250028",
                    "Back-Room PM-2411-BT Q529E65K5250099",
                ],
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
