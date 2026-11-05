"""Tests for the shipping tab's module-level wiring."""

import unittest

from shippy_gui import shipping_tab


class LogoPathTests(unittest.TestCase):
    """The logo stamped on labels must resolve to the bundled file."""

    def test_logo_path_points_at_the_packaged_asset(self):
        self.assertTrue(shipping_tab.LOGO_PATH.is_file(), shipping_tab.LOGO_PATH)


if __name__ == "__main__":
    unittest.main()
