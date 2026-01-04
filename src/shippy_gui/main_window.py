"""Main window for shippy-gui application."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar
from PySide6.QtGui import QAction

from shippy_gui.tabs.bulk_tab import BulkTab
from shippy_gui.tabs.individual_tab import IndividualTab
from shippy_gui.tabs.manual_tab import ManualTab
from shippy_gui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

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

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)

        # Create and add tabs
        self.individual_tab = IndividualTab()
        self.manual_tab = ManualTab()
        self.bulk_tab = BulkTab()

        self.tab_widget.addTab(self.individual_tab, "Individual")
        self.tab_widget.addTab(self.manual_tab, "Manual")
        self.tab_widget.addTab(self.bulk_tab, "Bulk")

        # Set tab widget as central widget
        self.setCentralWidget(self.tab_widget)

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
