"""Typed printer discovery models."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ibp_printing import PrinterCandidate


class PrinterTransport(str, Enum):
    """Known printer transport types."""

    USB = "usb"


@dataclass(frozen=True)
class PrinterInfo:
    """Printer metadata used for discovery and UI selection."""

    system_name: str
    is_default: bool = False
    transport: Optional[PrinterTransport] = None
    usb_id: Optional[str] = None

    @classmethod
    def from_candidate(cls, candidate: PrinterCandidate) -> "PrinterInfo":
        """Adapt an ibp-printing discovery candidate for the UI."""
        return cls(
            system_name=candidate.name,
            is_default=candidate.queue.is_default,
            transport=PrinterTransport.USB if candidate.vid_pid else None,
            usb_id=candidate.vid_pid,
        )
