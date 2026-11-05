"""Tests for reading the return address from the IBP server."""

import unittest
from unittest import mock

import requests

from shippy_gui.core.ibp_server import IbpServerError, fetch_return_address

SETTINGS = {
    "return_address": {
        "name": "INSIDE BOOKS PROJECT",
        "street1": "PO BOX 301029",
        "street2": None,
        "city": "AUSTIN",
        "state": "TX",
        "zipcode": "78703",
    },
    "unit_recipient_name": "ATTN: MAILROOM STAFF",
}


def response(body, status=200):
    """A requests.Response stand-in."""
    fake = mock.Mock()
    fake.json.return_value = body
    fake.raise_for_status.side_effect = (
        requests.HTTPError(f"{status} error") if status >= 400 else None
    )
    return fake


@mock.patch("shippy_gui.core.ibp_server.requests.get")
class FetchReturnAddressTests(unittest.TestCase):
    """fetch_return_address() against a mocked server."""

    def test_reads_shipping_settings_under_the_api_prefix(self, get):
        get.return_value = response(SETTINGS)

        for base in ("http://ibp.test/api", "http://ibp.test/api/"):
            with self.subTest(base=base):
                address = fetch_return_address(base)
                self.assertEqual(
                    get.call_args.args[0], "http://ibp.test/api/shipping-settings"
                )
                self.assertEqual(address.name, "INSIDE BOOKS PROJECT")
                self.assertEqual(address.street2, "")
                self.assertEqual(address.zipcode, "78703")

    def test_unreachable_server_raises(self, get):
        get.side_effect = requests.ConnectionError("refused")

        with self.assertRaisesRegex(IbpServerError, "could not reach"):
            fetch_return_address("http://ibp.test/api")

    def test_http_error_raises(self, get):
        get.return_value = response({"detail": "Not Found"}, status=404)

        with self.assertRaisesRegex(IbpServerError, "404"):
            fetch_return_address("http://ibp.test/api")

    def test_incomplete_address_raises(self, get):
        body = {"return_address": {**SETTINGS["return_address"], "city": ""}}
        get.return_value = response(body)

        with self.assertRaisesRegex(IbpServerError, "incomplete"):
            fetch_return_address("http://ibp.test/api")

    def test_unexpected_body_raises(self, get):
        get.return_value = response({"something": "else"})

        with self.assertRaisesRegex(IbpServerError, "unexpected response"):
            fetch_return_address("http://ibp.test/api")


if __name__ == "__main__":
    unittest.main()
