"""Unit tests for main window settings reload behavior."""

import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from shippy_gui.main_window import MainWindow


class MainWindowTests(unittest.TestCase):
    """Tests for main window settings handling."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("shippy_gui.main_window.SettingsDialog")
    @patch.object(MainWindow, "_apply_font_from_config")
    @patch.object(MainWindow, "_init_ui", lambda self: None)
    def test_open_settings_reloads_shipping_tab_on_success(
        self, mock_apply_font, mock_settings_dialog
    ):
        dialog = Mock()
        dialog.exec.return_value = True
        mock_settings_dialog.return_value = dialog

        window = MainWindow()
        window.status_bar = Mock()
        window.shipping_tab = Mock()
        window.shipping_tab.reload_config = Mock(return_value=True)

        window._open_settings()

        window.shipping_tab.reload_config.assert_called_once_with()
        mock_apply_font.assert_called_once_with()

    @patch("shippy_gui.main_window.SettingsDialog")
    @patch.object(MainWindow, "_apply_font_from_config")
    @patch.object(MainWindow, "_init_ui", lambda self: None)
    def test_open_settings_does_not_reload_when_dialog_is_cancelled(
        self, mock_apply_font, mock_settings_dialog
    ):
        dialog = Mock()
        dialog.exec.return_value = False
        mock_settings_dialog.return_value = dialog

        window = MainWindow()
        window.status_bar = Mock()
        window.shipping_tab = Mock()
        window.shipping_tab.reload_config = Mock()

        window._open_settings()

        window.shipping_tab.reload_config.assert_not_called()
        mock_apply_font.assert_not_called()


if __name__ == "__main__":
    unittest.main()
