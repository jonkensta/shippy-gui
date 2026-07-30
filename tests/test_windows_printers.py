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

    def test_parse_name_identifier_ignores_a_trailing_word_with_no_digits(self):
        """An ordinary descriptive name is not a serial number."""
        self.assertEqual(
            WindowsPrinterBackend.parse_name_identifier("Front Desk Printer"),
            (None, None),
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
                self.backend.get_present_usb_device_ids(),
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


class FakeDeviceContext:
    """Records GDI calls and optionally fails one of them."""

    def __init__(self, failing_call: str | None = None):
        self.calls: list[str] = []
        self._failing_call = failing_call

    def _record(self, call: str):
        self.calls.append(call)
        if call == self._failing_call:
            raise RuntimeError(f"{call} failed")

    def StartDoc(self, name):  # pylint: disable=invalid-name,unused-argument
        self._record("StartDoc")

    def StartPage(self):  # pylint: disable=invalid-name
        self._record("StartPage")

    def EndPage(self):  # pylint: disable=invalid-name
        self._record("EndPage")

    def EndDoc(self):  # pylint: disable=invalid-name
        self._record("EndDoc")

    def AbortDoc(self):  # pylint: disable=invalid-name
        self._record("AbortDoc")

    def CreatePrinterDC(self, name):  # pylint: disable=invalid-name,unused-argument
        self._record("CreatePrinterDC")

    def DeleteDC(self):  # pylint: disable=invalid-name
        self._record("DeleteDC")


class FakeWin32Ui:
    """Stand-in for the win32ui module that hands out one device context."""

    def __init__(self, context=None, create_error: Exception | None = None):
        self.context = context
        self._create_error = create_error

    def CreateDC(self):  # pylint: disable=invalid-name
        if self._create_error is not None:
            raise self._create_error
        return self.context


class PrinterContextTests(unittest.TestCase):
    """Tests that the device context is released exactly when it was acquired."""

    def test_success_path_opens_and_releases_the_context(self):
        context = FakeDeviceContext()

        with WindowsPrinterBackend._printer_context(
            FakeWin32Ui(context), "Front-Desk PM-2411-BT Q529E65K5250028"
        ) as yielded:
            self.assertIs(yielded, context)

        self.assertEqual(context.calls, ["CreatePrinterDC", "DeleteDC"])

    def test_queue_open_failure_still_releases_the_context(self):
        """A paused queue or broken driver must not leak the device context."""
        context = FakeDeviceContext(failing_call="CreatePrinterDC")

        with self.assertRaisesRegex(RuntimeError, "Could not open printer queue"):
            with WindowsPrinterBackend._printer_context(
                FakeWin32Ui(context), "Front-Desk PM-2411-BT Q529E65K5250028"
            ):
                self.fail("body must not run when the queue cannot be opened")

        self.assertEqual(context.calls, ["CreatePrinterDC", "DeleteDC"])

    def test_queue_open_failure_keeps_the_gdi_error_as_the_cause(self):
        context = FakeDeviceContext(failing_call="CreatePrinterDC")

        with self.assertRaises(RuntimeError) as caught:
            with WindowsPrinterBackend._printer_context(
                FakeWin32Ui(context), "Front-Desk"
            ):
                pass

        self.assertIsInstance(caught.exception.__cause__, RuntimeError)
        self.assertIn("CreatePrinterDC failed", str(caught.exception.__cause__))

    def test_context_creation_failure_is_reported_as_a_runtime_error(self):
        """With no context acquired there is nothing to release."""
        win32ui = FakeWin32Ui(create_error=OSError("no GDI handles left"))

        with self.assertRaisesRegex(RuntimeError, "printer device context"):
            with WindowsPrinterBackend._printer_context(win32ui, "Front-Desk"):
                self.fail("body must not run when CreateDC fails")

    def test_body_failure_releases_the_context_and_propagates_unwrapped(self):
        """Only open failures are translated; a draw failure is not one."""
        context = FakeDeviceContext()

        with self.assertRaisesRegex(ValueError, "draw failed"):
            with WindowsPrinterBackend._printer_context(
                FakeWin32Ui(context), "Front-Desk"
            ):
                raise ValueError("draw failed")

        self.assertEqual(context.calls, ["CreatePrinterDC", "DeleteDC"])


class PrintJobTests(unittest.TestCase):
    """Tests that print-job cleanup never runs ahead of its acquisition."""

    def test_success_path_opens_and_closes_the_job(self):
        context = FakeDeviceContext()

        with WindowsPrinterBackend._print_job(context, "Shipping Label"):
            pass

        self.assertEqual(context.calls, ["StartDoc", "StartPage", "EndPage", "EndDoc"])

    def test_body_failure_discards_the_job_instead_of_committing_it(self):
        """A half-drawn label must be aborted, not spooled as a finished document."""
        context = FakeDeviceContext()

        with self.assertRaises(ValueError):
            with WindowsPrinterBackend._print_job(context, "Shipping Label"):
                raise ValueError("draw failed")

        self.assertEqual(context.calls, ["StartDoc", "StartPage", "AbortDoc"])
        self.assertNotIn("EndDoc", context.calls)

    def test_start_doc_failure_surfaces_the_real_error(self):
        """GDI rejects the closers here, which would mask the real cause."""
        context = FakeDeviceContext(failing_call="StartDoc")

        with self.assertRaisesRegex(RuntimeError, "StartDoc failed"):
            with WindowsPrinterBackend._print_job(context, "Shipping Label"):
                self.fail("body must not run when StartDoc fails")

        self.assertEqual(context.calls, ["StartDoc"])

    def test_start_page_failure_discards_the_open_document(self):
        context = FakeDeviceContext(failing_call="StartPage")

        with self.assertRaisesRegex(RuntimeError, "StartPage failed"):
            with WindowsPrinterBackend._print_job(context, "Shipping Label"):
                self.fail("body must not run when StartPage fails")

        self.assertEqual(context.calls, ["StartDoc", "StartPage", "AbortDoc"])

    def test_end_page_failure_discards_the_job(self):
        """The page closer failing is still a failed label, not a finished one."""
        context = FakeDeviceContext(failing_call="EndPage")

        with self.assertRaisesRegex(RuntimeError, "EndPage failed"):
            with WindowsPrinterBackend._print_job(context, "Shipping Label"):
                pass

        self.assertEqual(
            context.calls, ["StartDoc", "StartPage", "EndPage", "AbortDoc"]
        )


if __name__ == "__main__":
    unittest.main()
