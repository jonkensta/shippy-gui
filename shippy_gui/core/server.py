"""IBP server API abstraction."""

from typing import Any, cast
from urllib.parse import urljoin, quote

import requests

from .models import IbpConfig


class Server:
    """Server API convenience class."""

    _url: str
    _timeout: float

    def __init__(self, url: str, timeout: float = 30.0):
        """Create server API convenience class from url."""
        self._url = url
        self._timeout = float(timeout)

    @classmethod
    def from_config(cls, config: IbpConfig) -> "Server":
        """Create a Server instance from a Pydantic config object."""
        return cls(url=str(config.url))

    def _get(self, path: str) -> dict | list:
        """Execute GET request to API endpoint."""
        url = urljoin(self._url, path)
        try:
            response = requests.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Resource not found: {path}") from e
            if e.response.status_code == 400:
                raise ValueError(f"Invalid request: {path}") from e
            raise
        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(f"Cannot connect to IBP server at {self._url}") from e
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request to {url} timed out") from e

    def unit_ids(self) -> dict[str, str]:
        """
        Get list of unit names with composite IDs (Texas only).

        Returns:
            dict mapping uppercase unit name to composite ID 'Jurisdiction-Name'
        """
        units = cast(list[dict[str, Any]], self._get("units"))
        unit_map = {}
        for unit in units:
            jurisdiction = unit["jurisdiction"]
            # Only include Texas units (Federal inmates receive individual packages only)
            if jurisdiction != "Texas":
                continue
            name = unit["name"]
            composite_id = f"{jurisdiction}-{name}"
            unit_map[name.upper()] = composite_id
        return unit_map

    def unit_address(self, composite_id: str) -> dict[str, str]:
        """
        Get unit address from its composite ID.

        Args:
            composite_id: Format 'Jurisdiction-Name' (e.g., 'Texas-GATESVILLE')

        Returns:
            dict with address fields: name, street1, street2, city, state, zipcode
        """
        parts = composite_id.split("-", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid composite_id format: {composite_id}")
        jurisdiction, name = parts

        # URL encode the name to handle spaces
        encoded_name = quote(name)

        unit = cast(dict[str, Any], self._get(f"units/{jurisdiction}/{encoded_name}"))

        # Extract address fields from unit object
        # Standard address dictionary construction pattern used throughout codebase
        # pylint: disable=duplicate-code
        return {
            "name": "ATTN: Mailroom Staff",
            "street1": unit["street1"],
            "street2": unit.get("street2", ""),
            "city": unit["city"],
            "state": unit["state"],
            "zipcode": unit["zipcode"],
        }

    def find_inmate(
        self, user_input: str
    ) -> tuple[dict[str, Any], str] | tuple[list[tuple[str, dict[str, Any]]], str]:
        """
        Find inmate using multiple strategies.

        Returns:
            tuple: (inmate_data, strategy_used) or (candidates, "multiple_matches")

        Strategies:
            1. Try as barcode ID format "TEX-12345678-0" or "FED-12345678-0" (ignore index)
            2. Try as inmate ID (any digit string) - search both jurisdictions
            3. Try as legacy request_id
        """
        user_input = user_input.strip()

        # Strategy 1: Try as barcode format (TEX-12345678-0 or FED-12345678-0)
        if user_input.startswith(("TEX-", "FED-")):
            try:
                parts = user_input.split("-")
                if (
                    len(parts) >= 2
                ):  # At minimum: code-inmateID, optionally: code-inmateID-index
                    code = parts[0]
                    inmate_id_str = parts[1]
                    # Ignore index (parts[2]) if present
                    jurisdiction = "Texas" if code == "TEX" else "Federal"
                    inmate_id = int(inmate_id_str)
                    inmate = cast(
                        dict[str, Any], self._get(f"inmates/{jurisdiction}/{inmate_id}")
                    )
                    return inmate, f"barcode ({user_input})"
            except (ValueError, requests.exceptions.RequestException, KeyError):
                # Fall through to next strategy if barcode parsing/lookup fails
                pass

        # Strategy 2: Try as inmate ID (any digit string)
        if user_input.isdigit():
            inmate_id = int(user_input)
            candidates: list[tuple[str, dict[str, Any]]] = []

            # Try both jurisdictions
            for jurisdiction in ["Texas", "Federal"]:
                try:
                    inmate = cast(
                        dict[str, Any], self._get(f"inmates/{jurisdiction}/{inmate_id}")
                    )
                    candidates.append((jurisdiction, inmate))
                except (ValueError, requests.exceptions.RequestException, KeyError):
                    # Inmate not in this jurisdiction, continue to next
                    pass

            if len(candidates) == 1:
                jurisdiction, inmate = candidates[0]
                return inmate, f"inmate ID ({jurisdiction}-{inmate_id})"
            if len(candidates) > 1:
                # Multiple matches - need user to choose
                return candidates, "multiple_matches"

            # Strategy 3: If no inmates found, try as legacy request_id
            try:
                inmate = cast(
                    dict[str, Any], self._get(f"inmates/by-request/{inmate_id}")
                )
                return inmate, f"legacy request ID ({inmate_id})"
            except (ValueError, requests.exceptions.RequestException, KeyError):
                # Legacy lookup failed, fall through to error
                pass

        # All strategies failed
        raise ValueError(f"Could not find inmate with input: {user_input}")
