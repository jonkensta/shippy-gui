"""Settings dialog for shippy-gui configuration."""

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
from shippy_gui.core.constants import (
    DEFAULT_FONT_SIZE,
    DEFAULT_WEIGHT_LBS,
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    WEIGHT_MAX_LBS,
    WEIGHT_MIN_LBS,
)
from shippy_gui.core.models import Config


class SettingsDialog(
    QDialog
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
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
        if not self._config_manager.load(parent_widget=self):
            return

        config = self._config_manager.config
        if config is None:
            return

        # Populate form fields
        self.easypost_key_input.setText(config.easypost.apikey)
        self.gmaps_key_input.setText(config.googlemaps.apikey)
        self.return_name_input.setText(config.return_address.name)
        self.return_street1_input.setText(config.return_address.street1)
        self.return_street2_input.setText(config.return_address.street2 or "")
        self.return_city_input.setText(config.return_address.city)
        self.return_state_input.setText(config.return_address.state)
        self.return_zipcode_input.setText(config.return_address.zipcode)
        self.font_size_input.setValue(config.get_font_size())
        self.default_weight_input.setValue(config.get_default_weight())
        self.log_file_input.setText(config.ui.log_file if config.ui else "")

    def _save_config(self):
        """Save configuration to config.ini file with validation."""
        # Build config dict from form inputs
        config_dict = {
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
        if self._config_manager.save(config, parent_widget=self):
            self.accept()
