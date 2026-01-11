"""Settings dialog for shippy-gui configuration."""
# pylint: disable=duplicate-code  # Common config loading and button layout patterns

import configparser
import os

from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from pydantic import ValidationError

from shippy_gui.core.models import Config


class SettingsDialog(QDialog):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Dialog for editing application settings."""

    def __init__(self, config_path: str, parent=None):
        """Initialize the settings dialog.

        Args:
            config_path: Path to the config.ini file
            parent: Parent widget
        """
        super().__init__(parent)
        self.config_path = config_path
        self._init_ui()
        self._load_config()

    def _init_ui(self):  # pylint: disable=too-many-statements
        """Initialize the user interface."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setModal(True)

        # Main layout
        main_layout = QVBoxLayout()

        # IBP Server section
        ibp_group = QGroupBox("IBP Server")
        ibp_layout = QFormLayout()
        self.ibp_url_input = QLineEdit()
        ibp_layout.addRow("URL:", self.ibp_url_input)
        ibp_group.setLayout(ibp_layout)
        main_layout.addWidget(ibp_group)

        # EasyPost API section
        easypost_group = QGroupBox("EasyPost API")
        easypost_layout = QFormLayout()
        self.easypost_key_input = QLineEdit()
        self.easypost_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        easypost_layout.addRow("API Key:", self.easypost_key_input)
        easypost_group.setLayout(easypost_layout)
        main_layout.addWidget(easypost_group)

        # Google Maps API section
        gmaps_group = QGroupBox("Google Maps API")
        gmaps_layout = QFormLayout()
        self.gmaps_key_input = QLineEdit()
        self.gmaps_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        gmaps_layout.addRow("API Key:", self.gmaps_key_input)
        gmaps_group.setLayout(gmaps_layout)
        main_layout.addWidget(gmaps_group)

        # Return Address section
        return_addr_group = QGroupBox("Return Address")
        return_addr_layout = QFormLayout()
        self.return_name_input = QLineEdit()
        self.return_street1_input = QLineEdit()
        self.return_street2_input = QLineEdit()
        self.return_city_input = QLineEdit()
        self.return_state_input = QLineEdit()
        self.return_zipcode_input = QLineEdit()
        return_addr_layout.addRow("Name:", self.return_name_input)
        return_addr_layout.addRow("Street 1:", self.return_street1_input)
        return_addr_layout.addRow("Street 2:", self.return_street2_input)
        return_addr_layout.addRow("City:", self.return_city_input)
        return_addr_layout.addRow("State:", self.return_state_input)
        return_addr_layout.addRow("ZIP Code:", self.return_zipcode_input)
        return_addr_group.setLayout(return_addr_layout)
        main_layout.addWidget(return_addr_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_config)
        save_button.setDefault(True)
        button_layout.addWidget(save_button)

        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)

    def _load_config(self):
        """Load configuration from config.ini file."""
        if not os.path.exists(self.config_path):
            QMessageBox.warning(
                self,
                "Config Not Found",
                f"Configuration file not found at: {self.config_path}\n\n"
                "Please create a config.ini file based on the template.",
            )
            return

        try:
            config_parser = configparser.ConfigParser()
            config_parser.read(self.config_path)

            # Convert to dict for Pydantic validation
            config_dict = {
                section: dict(config_parser[section])
                for section in config_parser.sections()
            }
            config = Config.model_validate(config_dict)

            # Populate form fields
            self.ibp_url_input.setText(str(config.ibp.url))
            self.easypost_key_input.setText(config.easypost.apikey)
            self.gmaps_key_input.setText(config.googlemaps.apikey)
            self.return_name_input.setText(config.return_address.name)
            self.return_street1_input.setText(config.return_address.street1)
            self.return_street2_input.setText(config.return_address.street2 or "")
            self.return_city_input.setText(config.return_address.city)
            self.return_state_input.setText(config.return_address.state)
            self.return_zipcode_input.setText(config.return_address.zipcode)

        except ValidationError as e:
            QMessageBox.critical(
                self,
                "Config Validation Error",
                f"Error loading configuration:\n\n{str(e)}",
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            QMessageBox.critical(
                self,
                "Config Load Error",
                f"Unexpected error loading configuration:\n\n{str(e)}",
            )

    def _save_config(self):
        """Save configuration to config.ini file with validation."""
        try:
            # Build config dict from form inputs
            config_dict = {
                "ibp": {
                    "url": self.ibp_url_input.text().strip(),
                },
                "easypost": {
                    "apikey": self.easypost_key_input.text().strip(),
                },
                "googlemaps": {
                    "apikey": self.gmaps_key_input.text().strip(),
                },
                "return_address": {
                    "name": self.return_name_input.text().strip(),
                    "street1": self.return_street1_input.text().strip(),
                    "street2": self.return_street2_input.text().strip(),
                    "city": self.return_city_input.text().strip(),
                    "state": self.return_state_input.text().strip(),
                    "zipcode": self.return_zipcode_input.text().strip(),
                },
            }

            # Validate with Pydantic
            config = Config.model_validate(config_dict)

            # Write to config.ini
            config_parser = configparser.ConfigParser()
            config_parser["ibp"] = {"url": config.ibp.url}
            config_parser["easypost"] = {"apikey": config.easypost.apikey}
            config_parser["googlemaps"] = {"apikey": config.googlemaps.apikey}
            config_parser["return_address"] = {
                "name": config.return_address.name,
                "street1": config.return_address.street1,
                "street2": config.return_address.street2 or "",
                "city": config.return_address.city,
                "state": config.return_address.state,
                "zipcode": config.return_address.zipcode,
            }

            with open(self.config_path, "w", encoding="utf-8") as f:
                config_parser.write(f)

            # Success
            self.accept()

        except ValidationError as e:
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Please fix the following errors:\n\n{str(e)}",
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            QMessageBox.critical(
                self,
                "Save Error",
                f"Error saving configuration:\n\n{str(e)}",
            )
