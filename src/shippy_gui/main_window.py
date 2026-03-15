"""Main window for shippy-gui application."""

import os
from typing import Optional

from PySide6.QtGui import QAction  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.config import get_font_size_from_path
from shippy_gui.core.font import apply_font_size
from shippy_gui.settings_dialog import SettingsDialog
from shippy_gui.shipping_tab import ShippingTab


class MainWindow(QMainWindow):  # pylint: disable=too-few-public-methods
    """Main application window for shipping label generation."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the main window.

        Args:
            config_path: Path to config.ini file. Defaults to config.ini in current directory.
        """
        super().__init__()
        self.config_path = config_path or os.path.join(os.getcwd(), "config.ini")
        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Shippy GUI - IBP Shipping Label Generator")
        self.setMinimumSize(800, 600)

        # Create and set shipping tab as central widget
        self.shipping_tab = ShippingTab(config_path=self.config_path)
        self.setCentralWidget(self.shipping_tab)

        # Create menu bar
        self._create_menu_bar()

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        # Settings action
        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        # Quit action
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self.config_path, self)
        if dialog.exec():
            # Config was saved successfully
            # Reapply font size from updated config
            self._apply_font_from_config()
            if self.shipping_tab.reload_config():
                self.status_bar.showMessage("Settings saved successfully", 3000)
            else:
                self.status_bar.showMessage(
                    "Settings saved, but some services could not be reloaded",
                    5000,
                )
        else:
            # Dialog was cancelled
            self.status_bar.showMessage("Settings cancelled", 3000)

    def _apply_font_from_config(self):
        """Apply font size from config to the application."""
        app = QApplication.instance()
        if app:
            font_size = get_font_size_from_path(self.config_path)
            apply_font_size(app, font_size)
