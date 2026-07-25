"""Unit tests for shipping tab service wiring and reload behavior."""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QMessageBox

from shippy_gui.core.pending_shipments import PendingShipmentJournal
from shippy_gui.shipping_coordinators import ShippingServices
from shippy_gui.shipping_tab import ShippingTab

BASE_INI = """[easypost]
apikey = ek_test

[googlemaps]
apikey = AIzaSyDUMMYKEYFORTESTSONLY1234567890

[return_address]
name = Inside Books Project
street1 = 827 W 12th St
city = Austin
state = TX
zipcode = 78701

[ui]
default_weight = 3
"""


class ShippingTabServiceTests(unittest.TestCase):
    """Tests for the shared ShippingServices holder."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.config_path = os.path.join(self._tempdir.name, "config.ini")
        with open(self.config_path, "w", encoding="utf-8") as handle:
            handle.write(BASE_INI)

    def test_bundled_logo_is_found_inside_the_package(self):
        """The assets directory lives next to the module, not one level up."""
        logo_path = ShippingTab._resolve_logo_path()

        self.assertIsNotNone(logo_path)
        assert logo_path is not None
        self.assertTrue(os.path.exists(logo_path))
        self.assertEqual(
            os.path.basename(os.path.dirname(os.path.dirname(logo_path))),
            "shippy_gui",
        )

    def test_tab_exposes_the_logo_to_the_shipment_flow(self):
        tab = ShippingTab(config_path=self.config_path)

        self.assertIsNotNone(tab.logo_path)

    def _tab_with_pending(self, shipment_service):
        """A tab whose journal already holds an unresolved shipment."""
        tab = ShippingTab(config_path=self.config_path)
        journal = PendingShipmentJournal(
            os.path.join(self._tempdir.name, "pending.json")
        )
        journal.record("shp_PAID", tracking_code="TRACK1")
        tab._services = ShippingServices(
            shipment_service=shipment_service, journal=journal
        )
        return tab, journal

    def _click(self, tab, label):
        """Run reconciliation, choosing the button with the given text."""
        chosen = {}

        class ScriptedPrompt(QMessageBox):
            """QMessageBox that picks a named button instead of blocking."""

            def exec(self):  # pylint: disable=invalid-name
                for button in self.buttons():
                    if button.text().replace("&", "") == label:
                        chosen["button"] = button
                        return 0
                raise AssertionError(f"no button named {label!r}")

            def clickedButton(self):  # pylint: disable=invalid-name
                return chosen.get("button")

        with patch("shippy_gui.shipping_tab.QMessageBox", ScriptedPrompt):
            tab.reconcile_pending_shipments()

    def test_reconcile_refunds_when_the_operator_says_it_did_not_print(self):
        service = Mock()
        tab, journal = self._tab_with_pending(service)

        self._click(tab, "Refund them")

        service.refund_shipment.assert_called_once_with("shp_PAID")
        self.assertEqual(journal.pending(), [])

    def test_reconcile_keeps_postage_when_the_operator_says_it_printed(self):
        service = Mock()
        tab, journal = self._tab_with_pending(service)

        self._click(tab, "They printed")

        service.refund_shipment.assert_not_called()
        self.assertEqual(journal.pending(), [])

    def test_dismissing_the_prompt_keeps_the_record_for_next_time(self):
        """Dismissal must not destroy the trail to unrefunded postage."""
        service = Mock()
        tab, journal = self._tab_with_pending(service)

        self._click(tab, "Decide later")

        service.refund_shipment.assert_not_called()
        self.assertEqual(
            [entry.shipment_id for entry in journal.pending()], ["shp_PAID"]
        )

    def test_failed_refund_keeps_the_record(self):
        service = Mock()
        service.refund_shipment.side_effect = RuntimeError("no network")
        tab, journal = self._tab_with_pending(service)

        with patch("shippy_gui.shipping_tab.show_error") as mock_error:
            self._click(tab, "Refund them")

        mock_error.assert_called_once()
        self.assertEqual(
            [entry.shipment_id for entry in journal.pending()], ["shp_PAID"]
        )

    def test_services_are_wired_on_construction(self):
        tab = ShippingTab(config_path=self.config_path)

        self.assertIsNotNone(tab.config)
        self.assertIsNotNone(tab.shipment_service)
        self.assertIsNotNone(tab.address_parser)
        self.assertIsNotNone(tab.shipment_flow)

    def test_failed_service_rebuild_leaves_the_holder_consistent(self):
        """A partial rebuild must not pair a new config with a stale service."""
        tab = ShippingTab(config_path=self.config_path)
        original_service = tab.shipment_service
        original_config = tab.config

        with (
            patch(
                "shippy_gui.shipping_tab.googlemaps.Client",
                side_effect=ValueError("Invalid API key provided."),
            ),
            patch("shippy_gui.shipping_tab.show_error") as mock_error,
        ):
            reloaded = tab.reload_config()

        self.assertFalse(reloaded)
        mock_error.assert_called_once()
        # Nothing was published, so config and service still belong together.
        self.assertIs(tab.shipment_service, original_service)
        self.assertIs(tab._services.config, original_config)

    def test_successful_reload_replaces_services_in_place(self):
        tab = ShippingTab(config_path=self.config_path)
        coordinator = tab.shipment_flow
        original_service = tab.shipment_service

        self.assertTrue(tab.reload_config())

        self.assertIsNot(tab.shipment_service, original_service)
        # Coordinators are not rebuilt; they read through the shared holder.
        self.assertIs(tab.shipment_flow, coordinator)
        self.assertIs(
            tab.shipment_flow._services.shipment_service, tab.shipment_service
        )


if __name__ == "__main__":
    unittest.main()
