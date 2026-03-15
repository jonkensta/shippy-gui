"""Typed printer discovery models."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


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
