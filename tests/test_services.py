"""Unit tests for the ShipmentService EasyPost wrapper."""

import unittest
from unittest.mock import patch

from shippy_gui.core.constants import (
    PARCEL_PREDEFINED_PACKAGE,
    SMALL_BOX_HEIGHT_IN,
    SMALL_BOX_LENGTH_IN,
    SMALL_BOX_WIDTH_IN,
)
from shippy_gui.core.models import ParcelConfig
from shippy_gui.core.services import ShipmentService, small_box_problem


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

    def test_buy_shipment_declares_large_dimensions_by_default(self):
        service = ShipmentService("ep_test", ParcelConfig())

        service.buy_shipment("from_id", "to_id", 96.0)

        kwargs = self.client.parcel.create.call_args.kwargs
        self.assertEqual(
            (kwargs["length"], kwargs["width"], kwargs["height"]), (20.0, 14.0, 10.0)
        )

    def test_buy_shipment_declares_twelve_inch_cube_for_small_box(self):
        parcel_config = ParcelConfig(length=22.0, width=16.0, height=12.0)
        service = ShipmentService("ep_test", parcel_config)

        service.buy_shipment("from_id", "to_id", 96.0, small_box=True)

        self.client.parcel.create.assert_called_once_with(
            predefined_package=PARCEL_PREDEFINED_PACKAGE,
            weight=96.0,
            length=12.0,
            width=12.0,
            height=12.0,
        )

    def test_small_box_still_buys_lowest_usps_rate(self):
        service = ShipmentService("ep_test", ParcelConfig())

        result = service.buy_shipment("from_id", "to_id", 96.0, small_box=True)

        shipment = self.client.shipment.create.return_value
        shipment.lowest_rate.assert_called_once_with(["USPS"])
        self.client.shipment.buy.assert_called_once_with(
            shipment.id, rate=shipment.lowest_rate.return_value
        )
        self.assertIs(result, self.client.shipment.buy.return_value)

    def test_buy_shipment_buys_lowest_rate_for_created_shipment(self):
        service = ShipmentService("ep_test", ParcelConfig())

        result = service.buy_shipment("from_id", "to_id", 48.0)

        shipment = self.client.shipment.create.return_value
        self.client.shipment.buy.assert_called_once_with(
            shipment.id, rate=shipment.lowest_rate.return_value
        )
        self.assertIs(result, self.client.shipment.buy.return_value)


class SmallBoxProblemTests(unittest.TestCase):
    """The declared small box must avoid dimensional weight and long-side fees."""

    def test_configured_small_box_is_valid(self):
        self.assertEqual(
            small_box_problem(
                SMALL_BOX_LENGTH_IN, SMALL_BOX_WIDTH_IN, SMALL_BOX_HEIGHT_IN
            ),
            "",
        )

    def test_sides_are_rounded_up_before_the_volume(self):
        # 15.5 x 11 x 10 = 1,705 as measured, but USPS counts 16 x 11 x 10.
        self.assertIn("1,760 cu in", small_box_problem(15.5, 11, 10))

    def test_long_side_is_rejected_even_under_one_cubic_foot(self):
        self.assertIn("over 22 in", small_box_problem(24, 9, 8))

    def test_one_cubic_foot_exactly_is_allowed(self):
        self.assertEqual(small_box_problem(18, 12, 8), "")

    @patch("shippy_gui.core.services.SMALL_BOX_LENGTH_IN", 24.0)
    @patch("shippy_gui.core.services.easypost.EasyPostClient")
    def test_invalid_small_box_buys_nothing(self, client_class):
        service = ShipmentService("ep_test", ParcelConfig())

        with self.assertRaises(ValueError):
            service.buy_shipment("from_id", "to_id", 96.0, small_box=True)

        client_class.return_value.shipment.buy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
