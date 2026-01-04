"""Entry point for shippy-gui application."""

import sys
from PySide6.QtWidgets import QApplication
from shippy_gui.main_window import MainWindow


def main():
    """Launch the shippy-gui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Shippy GUI")
    app.setOrganizationName("Inside Books Project")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
