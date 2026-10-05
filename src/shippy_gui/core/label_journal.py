"""Shared label journal glue: duplicate checks and label status tracking.

The journal itself lives in ibp-printing and is shared by every IBP app on the
machine, so a label bought in shippy (CLI) is seen here too. Its calls never
raise for journal problems; the wrappers below additionally make sure a
journal hiccup can never break shipping (a slow journal is bounded by a
timeout, and anything unexpected is logged and ignored).
"""

import concurrent.futures
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import time
from typing import Any, Callable, Optional, Sequence, TypeVar

import ibp_printing

from shippy_gui.core.models import AddressBase

logger = logging.getLogger(__name__)

APP_NAME = "shippy-gui"

# How far back a label for the same recipient counts as a possible duplicate.
DUPLICATE_WINDOW_HOURS = 12

# Upper bound on a journal call made from the UI thread. The journal is a
# small local file, so this only matters if the disk or a lock is stuck.
JOURNAL_TIMEOUT_S = 2.0

STATUS_PURCHASED = "purchased"
STATUS_PRINTED = "printed"
STATUS_QUEUED = "queued"
STATUS_CHECK_PRINTER = "check_printer"
STATUS_REFUNDED = "refunded"

T = TypeVar("T")


@dataclass(frozen=True)
class LabelIdentity:
    """Who a label is for, as the journal knows it."""

    recipient_key: str
    recipient_label: str


def identity_for(address: AddressBase) -> LabelIdentity:
    """Build the journal identity of a recipient address.

    shippy (CLI) builds the same key from the same fields, so both apps see
    each other's labels.
    """
    street = " ".join(part for part in (address.street1, address.street2) if part)
    key = ibp_printing.recipient_key(
        address.name, street, address.city, address.state, address.zipcode
    )
    label = f"{address.name}, {address.street1}, {address.city}, {address.state}"
    return LabelIdentity(recipient_key=key, recipient_label=label)


def tracking_ref(shipment: Any) -> str:
    """The journal's key for a shipment: tracking code, else shipment id."""
    return shipment.tracking_code or shipment.id


_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="label-journal"
)


def call_with_timeout(
    func: Callable[[], T], default: T, timeout_s: float = JOURNAL_TIMEOUT_S
) -> T:
    """Run a journal call, giving up (with ``default``) after ``timeout_s``."""
    future = _EXECUTOR.submit(func)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        logger.warning("Label journal did not answer within %.1f s", timeout_s)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Label journal call failed")
    return default


def find_duplicates(
    identity: LabelIdentity, timeout_s: float = JOURNAL_TIMEOUT_S
) -> list[Any]:
    """Recent labels for the same recipient; empty if the journal is unavailable."""
    return call_with_timeout(
        lambda: list(
            ibp_printing.find_duplicates(
                identity.recipient_key, within_hours=DUPLICATE_WINDOW_HOURS
            )
        ),
        [],
        timeout_s,
    )


def pending_labels() -> list[Any]:
    """Labels still waiting to print (call off the UI thread)."""
    return list(ibp_printing.pending_labels())


def record_purchase(identity: Optional[LabelIdentity], shipment: Any) -> Any:
    """Journal a just-bought label; returns the record (None if not journaled)."""
    if identity is None:
        return None
    try:
        return ibp_printing.record_purchase(
            recipient_key=identity.recipient_key,
            recipient_label=identity.recipient_label,
            tracking_code=tracking_ref(shipment),
            shipment_id=shipment.id,
            app=APP_NAME,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not journal purchase of %s", shipment.id)
        return None


def update_status(shipment: Any, status: str, *, file: Optional[Path] = None) -> None:
    """Journal a label's print outcome; never raises."""
    try:
        ibp_printing.update_status(
            tracking_ref(shipment), status, file=str(file) if file else None
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception("Could not journal status %s for %s", status, shipment.id)


def retry_meta(
    identity: Optional[LabelIdentity], shipment: Any, record: Any = None
) -> dict[str, Any]:
    """Metadata saved next to a queued label for the label watcher."""
    created = getattr(record, "created", None)
    meta: dict[str, Any] = {
        "tracking_code": tracking_ref(shipment),
        "shipment_id": shipment.id,
        "app": APP_NAME,
        # When postage was bought (epoch seconds, like the journal).
        "created": created if isinstance(created, (int, float)) else time.time(),
    }
    if identity is not None:
        meta["recipient_label"] = identity.recipient_label
        meta["recipient_key"] = identity.recipient_key
    return meta


def as_datetime(value: Any) -> Optional[datetime]:
    """Read a journal timestamp (epoch seconds) as local time."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone()
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return moment.astimezone() if moment.tzinfo else moment


def format_time(value: Any) -> str:
    """HH:MM of a journal timestamp (today), else a short date and time."""
    moment = as_datetime(value)
    if moment is None:
        return str(value or "?")
    if moment.date() == datetime.now(moment.tzinfo).date():
        return moment.strftime("%H:%M")
    return moment.strftime("%b %d %H:%M")


def describe_state(record: Any) -> str:
    """What happened to an earlier label, phrased after "is already"."""
    status = getattr(record, "status", "")
    if status == STATUS_QUEUED:
        return "queued — it will print automatically when the printer works"
    if status == STATUS_CHECK_PRINTER:
        return "waiting at the printer: check the printer before reprinting"
    if status == STATUS_PRINTED:
        return f"printed at {format_time(record.updated or record.created)}"
    if status == STATUS_REFUNDED:
        return f"refunded at {format_time(record.updated or record.created)}"
    return (
        f"bought at {format_time(record.created)} (its print outcome is unknown: "
        "check the printer before reprinting)"
    )


def duplicate_question(records: Sequence[Any]) -> str:
    """Ask whether to create a label although one already exists."""
    newest = records[0]  # ibp-printing lists the newest first
    text = (
        f"A label for {newest.recipient_label} is already "
        f"{describe_state(newest)} (tracking {newest.tracking_code})."
    )
    others = len(records) - 1
    if others:
        text += (
            f" {others} other label(s) were made for this address in the last "
            f"{DUPLICATE_WINDOW_HOURS} hours."
        )
    return f"{text} Create another label anyway?"
