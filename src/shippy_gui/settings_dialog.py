"""Settings dialog for shippy-gui configuration."""

from typing import Any

from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QSpinBox,
)
from pydantic import ValidationError

from shippy_gui.core.config_manager import ConfigManager
from shippy_gui.dialogs import show_config_error
from shippy_gui.core.constants import (
    DEFAULT_FONT_SIZE,
    DEFAULT_WEIGHT_LBS,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    WEIGHT_MAX_LBS,
    WEIGHT_MIN_LBS,
)
from shippy_gui.core.models import Config, ReturnAddressConfig
from shippy_gui.widgets.address_form import AddressForm


class SettingsDialog(
    QDialog
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes,too-many-locals
    """Dialog for editing application settings."""

    def __init__(self, config_path: str, parent=None):
        """Initialize the settings dialog.

        Args:
            config_path: Path to the config.ini file
            parent: Parent widget
        """
        super().__init__(parent)
        self._config_manager = ConfigManager(config_path)

        self._init_ui()
        self._load_config()

    def _init_ui(self):  # pylint: disable=too-many-statements
        """Initialize the user interface."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.setModal(True)

        # Main layout
        main_layout = QVBoxLayout()

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

        # IBP API section
        ibp_group = QGroupBox("IBP API")
        ibp_layout = QFormLayout()
        self.ibp_url_input = QLineEdit()
        self.ibp_url_input.setPlaceholderText("https://example.com")
        self.ibp_key_input = QLineEdit()
        self.ibp_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        ibp_layout.addRow("URL:", self.ibp_url_input)
        ibp_layout.addRow("API Key:", self.ibp_key_input)
        ibp_group.setLayout(ibp_layout)
        main_layout.addWidget(ibp_group)

        # Return Address section
        return_addr_group = QGroupBox("Return Address")
        return_addr_layout = QVBoxLayout()
        self.return_address_form = AddressForm(
            include_company=False,
            subject="return",
            output_model=ReturnAddressConfig,
        )
        return_addr_layout.addWidget(self.return_address_form)
        return_addr_group.setLayout(return_addr_layout)
        main_layout.addWidget(return_addr_group)

        # UI Settings section
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout()
        self.font_size_input = QSpinBox()
        self.font_size_input.setRange(FONT_SIZE_MIN, FONT_SIZE_MAX)
        self.font_size_input.setValue(DEFAULT_FONT_SIZE)
        self.font_size_input.setSuffix(" pt")
        ui_layout.addRow("Font Size:", self.font_size_input)
        self.log_file_input = QLineEdit()
        self.log_file_input.setPlaceholderText("shippy.log")
        self.log_file_input.setToolTip("Filename or path for application log file")
        ui_layout.addRow("Log File:", self.log_file_input)
        ui_group.setLayout(ui_layout)
        main_layout.addWidget(ui_group)

        # Shipping Defaults section
        shipping_group = QGroupBox("Shipping Defaults")
        shipping_layout = QFormLayout()
        self.default_weight_input = QSpinBox()
        self.default_weight_input.setRange(WEIGHT_MIN_LBS, WEIGHT_MAX_LBS)
        self.default_weight_input.setValue(DEFAULT_WEIGHT_LBS)
        self.default_weight_input.setSuffix(" lbs")
        self.default_weight_input.setToolTip("Default package weight for new shipments")
        shipping_layout.addRow("Default Weight:", self.default_weight_input)
        shipping_group.setLayout(shipping_layout)
        main_layout.addWidget(shipping_group)

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
        result = self._config_manager.load()
        if not result.ok:
            show_config_error(self, result)
            return

        config = self._config_manager.config
        if config is None:
            return

        # Populate form fields
        self.easypost_key_input.setText(config.easypost.apikey)
        self.gmaps_key_input.setText(config.googlemaps.apikey)
        if config.ibp:
            self.ibp_url_input.setText(str(config.ibp.url) if config.ibp.url else "")
            self.ibp_key_input.setText(config.ibp.apikey or "")
        self.return_address_form.set_address(config.return_address)
        self.font_size_input.setValue(config.get_font_size())
        self.default_weight_input.setValue(config.get_default_weight())
        self.log_file_input.setText(config.ui.log_file if config.ui else "")

    def _save_config(self):
        """Save configuration to config.ini file with validation."""
        # Build config dict from form inputs
        config_dict: dict[str, dict[str, Any]] = {
            "ui": {
                "font_size": self.font_size_input.value(),
                "default_weight": self.default_weight_input.value(),
                "log_file": self.log_file_input.text().strip(),
            },
            "easypost": {
                "apikey": self.easypost_key_input.text().strip(),
            },
            "googlemaps": {
                "apikey": self.gmaps_key_input.text().strip(),
            },
            "return_address": self.return_address_form.get_values(),
        }

        # Both IBP fields are optional. An empty URL must be omitted rather than
        # sent as "", which AnyHttpUrl rejects outright.
        ibp_url = self.ibp_url_input.text().strip()
        ibp_apikey = self.ibp_key_input.text().strip()
        if ibp_url or ibp_apikey:
            config_dict["ibp"] = {
                "url": ibp_url or None,
                "apikey": ibp_apikey or None,
            }

        # Validate with Pydantic
        try:
            config = Config.model_validate(config_dict)
        except ValidationError as e:
            QMessageBox.critical(
                self,
                "Validation Error",
                f"Please fix the following errors:\n\n{e}",
            )
            return

        # Save using ConfigManager
        save_result = self._config_manager.save(config)
        if not save_result.ok:
            show_config_error(self, save_result)
            return
        self.accept()
