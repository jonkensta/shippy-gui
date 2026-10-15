"""Unit tests for the quoted-rate summary shown after buying postage."""

import unittest
from types import SimpleNamespace

from shippy_gui.core.rates import summarize_rates


def rate(service, price, carrier="USPS"):
    """A minimal stand-in for an EasyPost Rate."""
    return SimpleNamespace(service=service, rate=f"{price:.2f}", carrier=carrier)


def shipment(rates, bought):
    """A minimal stand-in for a bought EasyPost Shipment."""
    return SimpleNamespace(rates=rates, selected_rate=bought)


class SummarizeRatesTests(unittest.TestCase):
    """Formatting of the Library Mail / Ground Advantage comparison."""

    def test_shows_both_prices_and_marks_the_cheapest_bought(self):
        library, ground = rate("LibraryMail", 9.12), rate("GroundAdvantage", 8.40)
        summary = summarize_rates(
            shipment([library, ground, rate("Priority", 12.0)], ground)
        )

        self.assertEqual(
            summary.text,
            "Library Mail $9.12 · Ground Advantage $8.40 → "
            "bought Ground Advantage (cheapest)",
        )
        self.assertFalse(summary.library_mail_missing)

    def test_library_mail_first_when_it_is_cheaper(self):
        library, ground = rate("LibraryMail", 5.57), rate("GroundAdvantage", 20.59)
        summary = summarize_rates(shipment([ground, library], library))

        self.assertEqual(
            summary.text,
            "Library Mail $5.57 · Ground Advantage $20.59 → "
            "bought Library Mail (cheapest)",
        )

    def test_warns_when_library_mail_was_not_quoted(self):
        ground = rate("GroundAdvantage", 8.40)
        summary = summarize_rates(shipment([ground, rate("Priority", 12.0)], ground))

        self.assertTrue(summary.library_mail_missing)
        self.assertTrue(
            summary.text.startswith("WARNING: no Library Mail rate was quoted.")
        )
        self.assertIn("Ground Advantage $8.40 → bought Ground Advantage", summary.text)

    def test_bought_service_outside_the_comparison_is_shown(self):
        library, priority = rate("LibraryMail", 9.0), rate("Priority", 12.0)
        summary = summarize_rates(shipment([library, priority], priority))

        self.assertEqual(
            summary.text,
            "Library Mail $9.00 · Priority Mail $12.00 → bought Priority Mail",
        )

    def test_ignores_other_carriers(self):
        library = rate("LibraryMail", 9.0)
        summary = summarize_rates(
            shipment([library, rate("Ground", 1.0, carrier="UPS")], library)
        )

        self.assertEqual(
            summary.text, "Library Mail $9.00 → bought Library Mail (cheapest)"
        )

    def test_no_rate_list_gives_no_summary(self):
        self.assertIsNone(summarize_rates(SimpleNamespace(rates=None)))
        self.assertIsNone(summarize_rates(object()))


if __name__ == "__main__":
    unittest.main()
