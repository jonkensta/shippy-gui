"""The single refund policy for shipments whose label was not printed.

The app must never leave purchased postage unprinted and unrefunded. Both
print paths - the background worker print and the system print dialog - refund
through this one class, and each instance is bound to the very
:class:`ShipmentService` that bought the shipment, so a settings reload part
way through a shipment cannot refund against a different EasyPost account.
"""

from dataclasses import dataclass
from typing import Any, Optional

from shippy_gui.core.services import ShipmentService


@dataclass(frozen=True)
class RefundOutcome:
    """Result of attempting to refund a shipment."""

    reason: str
    refunded: bool
    error: Optional[str] = None


class RefundPolicy:  # pylint: disable=too-few-public-methods
    """Refund shipments through the service that purchased them."""

    def __init__(self, shipment_service: ShipmentService):
        self._shipment_service = shipment_service

    def refund(self, shipment: Any, reason: str) -> RefundOutcome:
        """Request a refund, reporting the outcome rather than raising.

        Args:
            shipment: The purchased shipment to refund.
            reason: Why the refund is being requested, for presentation.

        Returns:
            A RefundOutcome describing what happened.
        """
        try:
            self._shipment_service.refund_shipment(shipment.id)
            return RefundOutcome(reason=reason, refunded=True)
        except Exception as error:  # pylint: disable=broad-exception-caught
            return RefundOutcome(reason=reason, refunded=False, error=str(error))
