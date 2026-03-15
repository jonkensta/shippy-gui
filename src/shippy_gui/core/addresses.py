"""Address parsing with Google Maps."""

import logging
from typing import Any, Optional
import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error

from shippy_gui.core.models import AutocompletePrediction, ParsedAddress

logger = logging.getLogger(__name__)


class AddressParser:
    """Address parser that uses Google Maps API."""

    gmaps: googlemaps.Client

    def __init__(self, gmaps: googlemaps.Client):
        self.gmaps = gmaps

    def parse_address_components(self, address_components) -> ParsedAddress:
        """Parse Google address components into the app's address model."""
        components_by_type = self._index_components(address_components)

        street_number = self._get_component_value(components_by_type, "street_number")
        route = self._get_component_value(components_by_type, "route")
        premise = self._get_component_value(components_by_type, "premise")

        street1 = self._build_street1(street_number, route, premise)
        has_conventional_street = bool(street_number and route)
        street2 = self._build_street2(components_by_type, has_conventional_street)
        city = self._first_component_value(
            components_by_type,
            [
                ("locality", "long_name"),
                # postal_town is mainly relevant outside the US but harmless as fallback.
                ("postal_town", "long_name"),
                ("sublocality_level_1", "long_name"),
            ],
        )
        state = self._get_component_value(
            components_by_type, "administrative_area_level_1", "short_name"
        )
        zipcode = self._build_zipcode(components_by_type)
        country = self._get_component_value(components_by_type, "country", "short_name")

        self._log_unmapped_components(components_by_type)

        return ParsedAddress(
            street1=street1,
            street2=street2,
            city=city,
            state=state,
            zipcode=zipcode,
            country=country,
        )

    def __call__(
        self, selected_address: str | AutocompletePrediction
    ) -> Optional[ParsedAddress]:
        """Parse an address string."""
        if isinstance(selected_address, AutocompletePrediction):
            geocode = self._geocode_prediction(selected_address)
        else:
            geocode = self._geocode_text(selected_address)

        if not geocode:
            return None

        first_result = geocode[0]
        address_components = first_result.get("address_components", [])
        return self.parse_address_components(address_components)

    def _geocode_prediction(
        self, prediction: AutocompletePrediction
    ) -> Optional[list[dict[str, Any]]]:
        """Geocode an autocomplete selection, preferring its stable place_id."""
        if prediction.place_id:
            geocode = self._safe_geocode(place_id=prediction.place_id)
            if geocode:
                return geocode

        return self._geocode_text(prediction.description)

    def _geocode_text(self, address_string: str) -> Optional[list[dict[str, Any]]]:
        """Geocode a free-form address string with the existing US bias."""
        return self._safe_geocode(address=address_string, region="us")

    def _safe_geocode(self, **kwargs) -> Optional[list[dict[str, Any]]]:
        """Wrap geocoding calls and normalize transport/API failures."""
        try:
            return self.gmaps.geocode(**kwargs)
        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ):
            return None

    @staticmethod
    def _index_components(
        address_components: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Index address components by type for deterministic lookup."""
        components_by_type: dict[str, list[dict[str, Any]]] = {}
        for component in address_components:
            for component_type in component.get("types", []):
                components_by_type.setdefault(component_type, []).append(component)
        return components_by_type

    @staticmethod
    def _get_component_value(
        components_by_type: dict[str, list[dict[str, Any]]],
        component_type: str,
        field_name: str = "long_name",
    ) -> Optional[str]:
        """Return the first value for a component type."""
        components = components_by_type.get(component_type, [])
        if not components:
            return None
        return components[0].get(field_name)

    def _first_component_value(
        self,
        components_by_type: dict[str, list[dict[str, Any]]],
        candidates: list[tuple[str, str]],
    ) -> Optional[str]:
        """Return the first non-empty value from ordered component candidates."""
        for component_type, field_name in candidates:
            value = self._get_component_value(
                components_by_type, component_type, field_name
            )
            if value:
                return value
        return None

    @staticmethod
    def _build_street1(
        street_number: Optional[str], route: Optional[str], premise: Optional[str]
    ) -> Optional[str]:
        """Build the first street line from documented address components."""
        if street_number and route:
            return f"{street_number} {route}"
        return premise

    def _build_street2(
        self,
        components_by_type: dict[str, list[dict[str, Any]]],
        has_conventional_street: bool,
    ) -> Optional[str]:
        """Build street2 from the best available supplemental components."""
        ordered_candidates: list[tuple[str, str]] = [
            ("subpremise", "long_name"),
            ("floor", "long_name"),
            ("room", "long_name"),
            ("post_box", "long_name"),
        ]
        has_explicit_supplemental = any(
            self._get_component_value(components_by_type, component_type)
            for component_type in ("subpremise", "floor", "room", "post_box")
        )
        if not has_conventional_street or has_explicit_supplemental:
            ordered_candidates.extend(
                [
                    ("establishment", "long_name"),
                    ("point_of_interest", "long_name"),
                ]
            )
        values: list[str] = []
        for component_type, field_name in ordered_candidates:
            value = self._get_component_value(
                components_by_type, component_type, field_name
            )
            if value and value not in values:
                values.append(value)
        if not values:
            return None
        return ", ".join(values)

    def _build_zipcode(
        self, components_by_type: dict[str, list[dict[str, Any]]]
    ) -> Optional[str]:
        """Build ZIP or ZIP+4 from documented postal code components."""
        postal_code = self._get_component_value(components_by_type, "postal_code")
        if not postal_code:
            return None

        postal_code_suffix = self._get_component_value(
            components_by_type, "postal_code_suffix"
        )
        if postal_code_suffix:
            return f"{postal_code}-{postal_code_suffix}"
        return postal_code

    @staticmethod
    def _log_unmapped_components(
        components_by_type: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Log component types that the parser currently ignores."""
        known_types = {
            "street_number",
            "route",
            "premise",
            "subpremise",
            "floor",
            "room",
            "post_box",
            "establishment",
            "point_of_interest",
            "locality",
            "postal_town",
            "sublocality_level_1",
            "administrative_area_level_1",
            "postal_code",
            "postal_code_suffix",
            "country",
        }
        unmapped_types = sorted(
            component_type
            for component_type in components_by_type
            if component_type not in known_types
        )
        if unmapped_types:
            logger.debug(
                "Ignoring unmapped address component types: %s", unmapped_types
            )
