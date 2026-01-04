"""Address parsing with Google Maps."""

import json
import os

import googlemaps  # type: ignore


class AddressParser:
    """Address parser that uses Google Maps API."""

    gmaps: googlemaps.Client

    def __init__(self, gmaps: googlemaps.Client):
        self.gmaps = gmaps

    def parse_address_components(self, address_components):
        """Parses the 'address_components' array using a mapping dictionary."""
        parsed = {}

        component_map = {
            "street_number": ("long_name", "street_number"),
            "subpremise": ("long_name", "street2"),
            "route": ("long_name", "street_name"),
            "locality": ("long_name", "city"),
            "administrative_area_level_1": ("short_name", "state"),
            "postal_code": ("long_name", "zipcode"),
            "country": ("short_name", "country"),
        }

        for component in address_components:
            types = set(component.get("types", [])).intersection(component_map)
            for component_type in types:
                input_key, output_key = component_map[component_type]
                parsed[output_key] = component.get(input_key)

        if "street_number" in parsed and "street_name" in parsed:
            street_number = parsed.pop("street_number")
            street_name = parsed.pop("street_name")
            parsed["street1"] = f"{street_number} {street_name}"

        return parsed

    def __call__(self, address_string: str):
        """Parse an address string."""
        try:
            geocode = self.gmaps.geocode(address_string, region="us")
        except (
            googlemaps.exceptions.ApiError,
            googlemaps.exceptions.Timeout,
            googlemaps.exceptions.TransportError,
        ):
            return None

        if not geocode:
            return None

        first_result = geocode[0]
        address_components = first_result.get("address_components", [])
        return self.parse_address_components(address_components)


def demo():
    """Run a demonstration of address parsing."""
    api_key = os.getenv("Maps_API_KEY")
    if not api_key:
        print("Error: Maps_API_KEY environment variable not set.")
        return

    gmaps = googlemaps.Client(key=api_key)
    parse_address = AddressParser(gmaps)

    chosen_address = "1600 Amphitheatre Parkway, Mountain View, CA 94043"
    address_parts = parse_address(chosen_address)
    if address_parts:
        print("\nParsed Address Components:")
        print(json.dumps(address_parts, indent=2))
