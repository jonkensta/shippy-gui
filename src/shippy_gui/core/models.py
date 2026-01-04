"""Pydantic models for configuration checking."""

from pydantic import BaseModel, HttpUrl


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

    ibp: IbpConfig
    easypost: EasypostConfig
    googlemaps: GoogleMapsConfig
    return_address: ReturnAddressConfig
