"""Unit tests for the ShipmentService EasyPost wrapper."""

import unittest
from unittest.mock import patch

from shippy_gui.core.constants import PARCEL_PREDEFINED_PACKAGE
from shippy_gui.core.models import ParcelConfig
from shippy_gui.core.services import ShipmentService


class ShipmentServiceTests(unittest.TestCase):
    """Tests for shipment creation via EasyPost."""

    def setUp(self):
        patcher = patch("shippy_gui.core.services.easypost.EasyPostClient")
        self.addCleanup(patcher.stop)
        self.client_class = patcher.start()
        self.client = self.client_class.return_value

    def test_buy_shipment_declares_parcel_dimensions(self):
        parcel_config = ParcelConfig(length=22.0, width=16.0, height=12.0)
        service = ShipmentService("ep_test", parcel_config)

        service.buy_shipment("from_id", "to_id", 48.0)

        self.client.parcel.create.assert_called_once_with(
            predefined_package=PARCEL_PREDEFINED_PACKAGE,
            weight=48.0,
            length=22.0,
            width=16.0,
            height=12.0,
        )

    def test_buy_shipment_buys_lowest_rate_for_created_shipment(self):
        service = ShipmentService("ep_test", ParcelConfig())

        result = service.buy_shipment("from_id", "to_id", 48.0)

        shipment = self.client.shipment.create.return_value
        self.client.shipment.buy.assert_called_once_with(
            shipment.id, rate=shipment.lowest_rate.return_value
        )
        self.assertIs(result, self.client.shipment.buy.return_value)


if __name__ == "__main__":
    unittest.main()
