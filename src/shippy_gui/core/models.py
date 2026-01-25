"""Pydantic models for configuration checking."""

from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


class UiConfig(BaseModel):
    """Model for UI configuration."""

    font_size: int = 11

    @field_validator("font_size")
    @classmethod
    def validate_font_size(cls, v: int) -> int:
        """Validate font size is within reasonable bounds."""
        if v < 8:
            raise ValueError("Font size must be at least 8")
        if v > 24:
            raise ValueError("Font size must be at most 24")
        return v


class IbpConfig(BaseModel):
    """Model for IBP configuration."""

    url: HttpUrl


class ReturnAddressConfig(BaseModel):
    """Model for return address configuration."""

    name: str
    street1: str
    street2: str = ""
    city: str
    state: str
    zipcode: str


class EasypostConfig(BaseModel):
    """Model for Easypost configuration."""

    apikey: str


class GoogleMapsConfig(BaseModel):
    """Model for Google Maps configuration."""

    apikey: str


class Config(BaseModel):
    """Model for application configuration."""

    ui: Optional[UiConfig] = None
    ibp: IbpConfig
    easypost: EasypostConfig
    googlemaps: GoogleMapsConfig
    return_address: ReturnAddressConfig

    def get_font_size(self) -> int:
        """Get font size with default fallback."""
        return self.ui.font_size if self.ui else 11
