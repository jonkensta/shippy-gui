"""Unit tests for shipping tab service wiring and reload behavior."""

import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

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
