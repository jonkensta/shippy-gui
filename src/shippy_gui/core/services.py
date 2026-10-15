"""Business logic services."""

import math
from typing import Any

import easypost  # type: ignore[import-not-found] # pylint: disable=import-error

from shippy_gui.core.constants import (
    SHIPMENT_CARRIER,
    SHIPMENT_SERVICE,
    PARCEL_PREDEFINED_PACKAGE,
    SMALL_BOX_HEIGHT_IN,
    SMALL_BOX_LENGTH_IN,
    SMALL_BOX_MAX_CUBIC_IN,
    SMALL_BOX_MAX_SIDE_IN,
    SMALL_BOX_WIDTH_IN,
)
from shippy_gui.core.models import AddressBase, ParcelConfig


def small_box_problem(length: float, width: float, height: float) -> str:
    """Why a box can't be declared as "small", or "" if it can.

    Matches USPS: each side is rounded UP to a whole inch, the rounded volume
    must be at most SMALL_BOX_MAX_CUBIC_IN (no dimensional weight), and no side
    may exceed SMALL_BOX_MAX_SIDE_IN (no Ground Advantage length surcharge).
    """
    sides = [math.ceil(side) for side in (length, width, height)]
    if min(sides) <= 0:
        return "every side must be positive"
    volume = sides[0] * sides[1] * sides[2]
    if volume > SMALL_BOX_MAX_CUBIC_IN:
        return (
            f"{sides[0]}x{sides[1]}x{sides[2]} in (rounded up) is {volume:,} cu in, "
            f"over {SMALL_BOX_MAX_CUBIC_IN:,}"
        )
    if max(sides) > SMALL_BOX_MAX_SIDE_IN:
        return f"a side of {max(sides)} in is over {SMALL_BOX_MAX_SIDE_IN} in"
    return ""


class ShipmentService:
    """Service for handling EasyPost shipment logic."""

    def __init__(self, api_key: str, parcel_config: ParcelConfig):
        self.client = easypost.EasyPostClient(api_key)
        self.parcel_config = parcel_config

    def create_address(self, address: AddressBase) -> Any:
        """Create an address in EasyPost."""
        data = address.to_easypost_dict()
        return self.client.address.create(**data)

    def verify_address(self, address_id: str) -> Any:
        """Verify an existing address ID."""
        return self.client.address.verify(address_id)

    def buy_shipment(
        self,
        from_addr_id: str,
        to_addr_id: str,
        weight_oz: float,
        *,
        small_box: bool = False,
    ) -> Any:
        """Create a shipment, find the lowest rate, and buy postage.

        ``small_box`` declares the parcel as a 12 in cube (at most one cubic
        foot), so Ground Advantage is priced on actual weight; otherwise the
        configured, larger dimensions are declared.
        """
        if small_box:
            problem = small_box_problem(
                SMALL_BOX_LENGTH_IN, SMALL_BOX_WIDTH_IN, SMALL_BOX_HEIGHT_IN
            )
            if problem:
                raise ValueError(f"Invalid small-box size: {problem}")
            length, width, height = (
                SMALL_BOX_LENGTH_IN,
                SMALL_BOX_WIDTH_IN,
                SMALL_BOX_HEIGHT_IN,
            )
        else:
            length = self.parcel_config.length
            width = self.parcel_config.width
            height = self.parcel_config.height
        parcel = self.client.parcel.create(
            predefined_package=PARCEL_PREDEFINED_PACKAGE,
            weight=weight_oz,
            length=length,
            width=width,
            height=height,
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
