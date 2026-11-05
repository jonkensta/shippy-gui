"""Read the return address from the IBP server, as shippy does.

The server keeps one return address for every label (GET /shipping-settings),
so the two shipping apps can't drift apart. The backend is served under
``/api`` behind nginx (``http://host/api``); the base URL is normalized to end
with one slash so ``urljoin`` keeps that prefix.
"""

from urllib.parse import urljoin

import requests
from pydantic import ValidationError

from shippy_gui.core.models import ReturnAddressConfig

SHIPPING_SETTINGS_PATH = "shipping-settings"
TIMEOUT_SECONDS = 15.0


class IbpServerError(Exception):
    """The return address could not be read from the IBP server."""


def fetch_return_address(
    base_url: str, timeout: float = TIMEOUT_SECONDS
) -> ReturnAddressConfig:
    """Get the organization's return address from the IBP server.

    Raises:
        IbpServerError: the server could not be reached, answered with an
            error, or sent an address that is incomplete.
    """
    url = urljoin(base_url.rstrip("/") + "/", SHIPPING_SETTINGS_PATH)
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        address = response.json()["return_address"]
        return ReturnAddressConfig.model_validate(
            {**address, "street2": address.get("street2") or ""}
        )
    except requests.RequestException as error:
        raise IbpServerError(f"could not reach {url}: {error}") from error
    except (ValueError, KeyError, TypeError) as error:
        # ValidationError is a ValueError; so is a body that isn't JSON.
        detail = (
            "the server's return address is incomplete"
            if isinstance(error, ValidationError)
            else "unexpected response"
        )
        raise IbpServerError(f"{detail} from {url}: {error}") from error
