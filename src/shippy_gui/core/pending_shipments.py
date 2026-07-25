"""Durable record of postage that was bought but not yet resolved.

Buying postage and confirming the label printed are two separate steps, and the
app can die in between - most easily on the print-dialog path, where the dialog
inherently needs the UI thread. Anything recorded here and never cleared is
money that may have been spent for nothing.

The journal is deliberately dumb: append a shipment when postage is bought,
remove it once the label is confirmed printed or confirmed refunded. Whatever
is still listed at startup is unresolved and needs a human decision, because
the app cannot tell "crashed before printing" from "printed, then crashed".
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

PENDING_SHIPMENTS_FILENAME = "pending_shipments.json"


@dataclass(frozen=True)
class PendingShipment:
    """A purchased shipment whose outcome was never recorded."""

    shipment_id: str
    tracking_code: Optional[str] = None
    recorded_at: Optional[str] = None


def journal_path_for(config_path: str) -> str:
    """Resolve the journal path that sits beside the given config file."""
    return os.path.join(os.path.dirname(config_path), PENDING_SHIPMENTS_FILENAME)


class PendingShipmentJournal:
    """File-backed list of purchased-but-unresolved shipments.

    Every method is failure-tolerant: a broken or unreadable journal must never
    stop the operator from printing labels, so problems are logged and treated
    as an empty journal rather than raised.
    """

    def __init__(self, path: str):
        self._path = path

    @property
    def path(self) -> str:
        """Path of the backing file."""
        return self._path

    @property
    def corrupt_path(self) -> str:
        """Where unreadable journal content is moved for inspection."""
        return f"{self._path}.corrupt"

    def record(
        self,
        shipment_id: str,
        tracking_code: Optional[str] = None,
        recorded_at: Optional[str] = None,
    ) -> bool:
        """Note that postage was bought for a shipment.

        Returns:
            True if the record is on disk. False means this shipment is not
            recoverable automatically and the caller must say so out loud.
        """
        if not shipment_id:
            return False
        entries = {entry.shipment_id: entry for entry in self.pending()}
        entries[shipment_id] = PendingShipment(
            shipment_id=shipment_id,
            tracking_code=tracking_code,
            recorded_at=recorded_at,
        )
        return self._write(list(entries.values()))

    def clear(self, shipment_id: str) -> bool:
        """Drop a shipment whose outcome is now known."""
        if not shipment_id:
            return False
        remaining = [
            entry for entry in self.pending() if entry.shipment_id != shipment_id
        ]
        return self._write(remaining)

    def pending(self) -> list[PendingShipment]:
        """Return shipments recorded but never resolved."""
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError):
            self._quarantine("unreadable")
            return []

        if not isinstance(raw, list):
            self._quarantine("unexpected content")
            return []

        entries = []
        malformed = 0
        for item in raw:
            if not isinstance(item, dict) or not item.get("shipment_id"):
                # A damaged entry may be the only trace of unrefunded
                # postage, so it is counted rather than quietly dropped.
                malformed += 1
                continue
            entries.append(
                PendingShipment(
                    shipment_id=str(item["shipment_id"]),
                    tracking_code=item.get("tracking_code"),
                    recorded_at=item.get("recorded_at"),
                )
            )

        if malformed:
            self._preserve_for_inspection(f"{malformed} unreadable entry(s)")

        return entries

    def _preserve_for_inspection(self, reason: str) -> None:
        """Copy a partly-damaged journal aside, keeping the usable entries.

        Unlike :meth:`_quarantine` this does not move the file: the readable
        entries still need to be reconciled. The copy exists so the operator
        can be told, and can go looking for what was lost.
        """
        logger.error(
            "Pending-shipment journal %s has %s; copying to %s",
            self._path,
            reason,
            self.corrupt_path,
        )
        if os.path.exists(self.corrupt_path):
            return
        try:
            shutil.copyfile(self._path, self.corrupt_path)
        except OSError:
            logger.error("Could not copy %s aside", self._path, exc_info=True)

    def _quarantine(self, reason: str) -> None:
        """Move an unusable journal aside so the operator can be told.

        Silently discarding it would hide shipments that may be unrefunded.
        """
        logger.error(
            "Pending-shipment journal %s is %s; moving to %s",
            self._path,
            reason,
            self.corrupt_path,
        )
        try:
            os.replace(self._path, self.corrupt_path)
        except OSError:
            logger.error("Could not quarantine %s", self._path, exc_info=True)

    def _write(self, entries: list[PendingShipment]) -> bool:
        """Persist the journal, replacing the file atomically."""
        payload = [
            {
                "shipment_id": entry.shipment_id,
                "tracking_code": entry.tracking_code,
                "recorded_at": entry.recorded_at,
            }
            for entry in entries
        ]
        temp_path = f"{self._path}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._path)
            return True
        except OSError:
            logger.error("Could not write %s", self._path, exc_info=True)
            try:
                os.remove(temp_path)
            except OSError:
                pass
            return False
