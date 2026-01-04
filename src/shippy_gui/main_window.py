"""Main window for shippy-gui application."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QStatusBar
from PySide6.QtGui import QAction

from shippy_gui.tabs.shipping_tab import ShippingTab
from shippy_gui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Main application window for shipping label generation."""

    def __init__(self, config_path: str = None):
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
            self.status_bar.showMessage("Settings saved successfully", 3000)
            # Tabs can reload config if needed in future phases
        else:
            # Dialog was cancelled
            self.status_bar.showMessage("Settings cancelled", 3000)
