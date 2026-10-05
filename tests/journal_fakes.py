"""In-memory stand-in for ibp-printing's shared label journal.

Tests must never touch the real journal on the developer's machine, so test
cases that run the shipment flow install this fake in place of the
``ibp_printing`` module as seen by ``shippy_gui.core.label_journal``.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from unittest.mock import patch

import ibp_printing


@dataclass
class FakeRecord:  # pylint: disable=too-many-instance-attributes
    """Mirror of ibp_printing.LabelRecord."""

    tracking_code: str
    shipment_id: str
    recipient_key: str
    recipient_label: str
    app: str
    status: str
    created: float
    updated: float
    file: Optional[str] = None


class FakeJournal:
    """Records journal calls; duplicates and pending labels are preset."""

    PrintError = ibp_printing.PrintError

    def __init__(self):
        self.records: dict[str, FakeRecord] = {}
        self.purchases: list[dict] = []
        self.status_updates: list[tuple] = []
        self.duplicates: list[FakeRecord] = []
        self.pending: list[FakeRecord] = []
        self.duplicate_queries: list[tuple] = []

    @staticmethod
    def recipient_key(name, street, city, state, zip_code) -> str:
        """Deterministic key built from the address parts."""
        return "|".join(
            str(part).lower() for part in (name, street, city, state, zip_code)
        )

    def record_purchase(self, **kwargs) -> FakeRecord:
        """Remember a purchase and return its record."""
        self.purchases.append(kwargs)
        now = datetime(2026, 10, 4, 9, 30).timestamp()
        record = FakeRecord(status="purchased", created=now, updated=now, **kwargs)
        self.records[kwargs["tracking_code"]] = record
        return record

    def update_status(self, tracking_code, status, *, file=None) -> None:
        """Remember a status change."""
        self.status_updates.append((tracking_code, status, file))

    def find_duplicates(self, recipient_key, *, within_hours=12) -> list:
        """Return the preset duplicates."""
        self.duplicate_queries.append((recipient_key, within_hours))
        return list(self.duplicates)

    def pending_labels(self) -> list:
        """Return the preset pending labels."""
        return list(self.pending)

    def statuses(self) -> list[str]:
        """Just the statuses, in order."""
        return [status for _tracking, status, _file in self.status_updates]


def install_fake_journal(test_case) -> FakeJournal:
    """Swap the journal for a fake for the rest of ``test_case``."""
    fake = FakeJournal()
    patcher = patch("shippy_gui.core.label_journal.ibp_printing", fake)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return fake


def make_record(**overrides) -> FakeRecord:
    """A journal record with sensible defaults."""
    moment = datetime.now().replace(hour=9, minute=41).timestamp()
    values = {
        "tracking_code": "9400OLD",
        "shipment_id": "shp_old",
        "recipient_key": "key",
        "recipient_label": "Jane Doe, 123 Prison Rd, Huntsville, TX",
        "app": "shippy",
        "status": "queued",
        "created": moment,
        "updated": moment,
    }
    values.update(overrides)
    return FakeRecord(**values)
