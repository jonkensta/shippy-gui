"""Pydantic models for configuration checking."""

from typing import Optional
from pydantic import BaseModel, field_validator

from shippy_gui.core.constants import (
    DEFAULT_FONT_SIZE,
    FONT_SIZE_MIN,
    FONT_SIZE_MAX,
    SHIPMENT_COUNTRY,
)


class UiConfig(BaseModel):
    """Model for UI configuration."""

    font_size: int = DEFAULT_FONT_SIZE

    @field_validator("font_size")
    @classmethod
    def validate_font_size(cls, v: int) -> int:
        """Validate font size is within reasonable bounds."""
        if v < FONT_SIZE_MIN:
            raise ValueError(f"Font size must be at least {FONT_SIZE_MIN}")
        if v > FONT_SIZE_MAX:
            raise ValueError(f"Font size must be at most {FONT_SIZE_MAX}")
        return v


class AddressBase(BaseModel):
    """Base model for address configuration."""

    name: str
    company: Optional[str] = None
    street1: str
    street2: str = ""
    city: str
    state: str
    zipcode: str

    def to_easypost_dict(self) -> dict:
        """Convert to EasyPost address dictionary."""
        data = self.model_dump(exclude_none=True)
        # EasyPost uses 'zip' instead of 'zipcode'
        data["zip"] = data.pop("zipcode")
        data["country"] = SHIPMENT_COUNTRY
        data["phone"] = ""
        return data


class ReturnAddressConfig(AddressBase):
    """Model for return address configuration."""


class RecipientAddress(AddressBase):
    """Model for recipient address."""


class EasypostConfig(BaseModel):
    """Model for Easypost configuration."""

    apikey: str


class GoogleMapsConfig(BaseModel):
    """Model for Google Maps configuration."""

    apikey: str


class Config(BaseModel):
    """Model for application configuration."""

    ui: Optional[UiConfig] = None
    easypost: EasypostConfig
    googlemaps: GoogleMapsConfig
    return_address: ReturnAddressConfig

    def get_font_size(self) -> int:
        """Get font size with default fallback."""
        return self.ui.font_size if self.ui else DEFAULT_FONT_SIZE
