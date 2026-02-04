"""Business logic services."""

from typing import Any

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error

from shippy_gui.core.constants import (
    SHIPMENT_CARRIER,
    SHIPMENT_SERVICE,
    PARCEL_PREDEFINED_PACKAGE,
)
from shippy_gui.core.models import AddressBase


class ShipmentService:
    """Service for handling EasyPost shipment logic."""

    def __init__(self, api_key: str):
        self.client = easypost.EasyPostClient(api_key)

    def create_address(self, address: AddressBase) -> Any:
        """Create an address in EasyPost."""
        data = address.to_easypost_dict()
        return self.client.address.create(**data)

    def verify_address(self, address_id: str) -> Any:
        """Verify an existing address ID."""
        return self.client.address.verify(address_id)

    def buy_shipment(
        self, from_addr_id: str, to_addr_id: str, weight_oz: float
    ) -> Any:
        """Create a shipment, find the lowest rate, and buy postage."""
        parcel = self.client.parcel.create(
            predefined_package=PARCEL_PREDEFINED_PACKAGE, weight=weight_oz
        )

        shipment = self.client.shipment.create(
            from_address={"id": from_addr_id},
            to_address={"id": to_addr_id},
            parcel=parcel,
            options={"special_rates_eligibility": SHIPMENT_SERVICE},
        )

        rate = shipment.lowest_rate([SHIPMENT_CARRIER])
        return self.client.shipment.buy(shipment.id, rate=rate)

    def refund_shipment(self, shipment_id: str) -> None:
        """Refund a shipment."""
        self.client.shipment.refund(shipment_id)
