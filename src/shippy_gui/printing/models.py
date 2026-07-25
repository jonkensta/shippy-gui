"""Typed printer discovery models."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PrinterTransport(str, Enum):
    """Known printer transport types."""

    USB = "usb"


class PrintDialogResult(str, Enum):
    """Outcome of showing the system print dialog."""

    PRINTED = "printed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class PrinterInfo:
    """Printer metadata used for discovery and UI selection."""

    system_name: str
    is_default: bool = False
    transport: Optional[PrinterTransport] = None
    usb_id: Optional[str] = None
