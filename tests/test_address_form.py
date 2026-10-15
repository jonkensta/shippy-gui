"""Unit tests for the address form's "new package" signal."""

import unittest

from PySide6.QtWidgets import QApplication

from shippy_gui.widgets.address_form import AddressForm


class AddressReplacedSignalTests(unittest.TestCase):
    """address_replaced fires when the whole address changes, not on typing."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.form = AddressForm()
        self.emitted: list[bool] = []
        self.form.address_replaced.connect(lambda: self.emitted.append(True))

    def test_clear_emits(self):
        self.form.clear()
        self.assertEqual(self.emitted, [True])

    def test_set_address_emits(self):
        self.form.set_address({"street1": "1 Main St", "city": "Austin"})
        self.assertEqual(self.emitted, [True])

    def test_merge_address_emits(self):
        self.form.merge_address({"zipcode": "78701"})
        self.assertEqual(self.emitted, [True])

    def test_typing_in_a_field_does_not_emit(self):
        self.form.name_input.setText("Jane Doe")
        self.assertEqual(self.emitted, [])


if __name__ == "__main__":
    unittest.main()
