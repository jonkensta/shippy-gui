"""Describe the USPS rates EasyPost quoted for a bought shipment."""

from dataclasses import dataclass
from typing import Any, Optional

from shippy_gui.core.constants import SHIPMENT_CARRIER

LIBRARY_MAIL = "LibraryMail"
GROUND_ADVANTAGE = "GroundAdvantage"

# Services always shown side by side, in this order, when they were quoted.
COMPARED_SERVICES = (LIBRARY_MAIL, GROUND_ADVANTAGE)

SERVICE_NAMES = {
    LIBRARY_MAIL: "Library Mail",
    GROUND_ADVANTAGE: "Ground Advantage",
    "MediaMail": "Media Mail",
    "Priority": "Priority Mail",
    "Express": "Priority Mail Express",
}


@dataclass(frozen=True)
class RateSummary:
    """One-line comparison of the quoted rates and the one that was bought."""

    text: str
    library_mail_missing: bool


def service_name(service: str) -> str:
    """Volunteer-facing name of an EasyPost USPS service code."""
    return SERVICE_NAMES.get(service, service)


def _price(rate: Any) -> Optional[float]:
    try:
        return float(rate.rate)
    except (AttributeError, TypeError, ValueError):
        return None


def summarize_rates(shipment: Any) -> Optional[RateSummary]:
    """Compare the quoted USPS rates with the one bought.

    Returns None when the shipment carries no usable rate list (nothing to
    show). Example text: "Library Mail $9.12 · Ground Advantage $8.40 →
    bought Ground Advantage (cheapest)".
    """
    rates = getattr(shipment, "rates", None)
    if not isinstance(rates, (list, tuple)):
        return None
    quoted: dict[str, float] = {}
    for rate in rates:
        price = _price(rate)
        if getattr(rate, "carrier", None) != SHIPMENT_CARRIER or price is None:
            continue
        service = str(getattr(rate, "service", ""))
        quoted[service] = min(price, quoted.get(service, price))

    selected = getattr(shipment, "selected_rate", None)
    bought_service = str(getattr(selected, "service", "") or "")
    bought_price = _price(selected) if selected is not None else None
    if not quoted and bought_price is None:
        return None

    shown = [service for service in COMPARED_SERVICES if service in quoted]
    if bought_service and bought_service not in shown and bought_service in quoted:
        shown.append(bought_service)
    parts = [f"{service_name(s)} ${quoted[s]:.2f}" for s in shown]

    text = " · ".join(parts)
    if bought_service:
        cheapest = bought_price is not None and all(
            bought_price <= price for price in quoted.values()
        )
        bought = f"bought {service_name(bought_service)}"
        if cheapest:
            bought += " (cheapest)"
        text = f"{text} → {bought}" if text else bought

    missing = LIBRARY_MAIL not in quoted
    if missing:
        text = f"WARNING: no Library Mail rate was quoted. {text}"
    return RateSummary(text=text, library_mail_missing=missing)
