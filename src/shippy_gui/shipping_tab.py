"""Unified shipping tab with manual address entry."""

# pylint: disable=duplicate-code  # Intentional patterns shared with settings_dialog

from pathlib import Path
from typing import Optional

import googlemaps  # type: ignore[import-not-found] # pylint: disable=import-error
from PySide6.QtWidgets import (  # type: ignore[import-untyped] # pylint: disable=no-name-in-module
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLineEdit,
    QLabel,
)
from PySide6.QtCore import Qt  # type: ignore[import-untyped] # pylint: disable=no-name-in-module

from shippy_gui.core.addresses import AddressParser
from shippy_gui.core.config_manager import ConfigManager
from shippy_gui.core.services import ShipmentService
from shippy_gui.shipping_coordinators import (
    AddressLookupCoordinator,
    ShipmentFlowCoordinator,
    ShippingStatusPresenter,
)
from shippy_gui.widgets.autocomplete import (
    GoogleMapsCompleter,
    setup_google_maps_autocomplete,
)
from shippy_gui.widgets.address_form import AddressForm
from shippy_gui.widgets.shipment_controls import ShipmentControls


class ShippingTab(QWidget):
    """Tab for unified shipping with address lookup."""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, config_path: Optional[str] = None, parent=None):
        """Initialize the shipping tab."""
        super().__init__(parent)
        self._config_manager = ConfigManager(config_path)

        self.gmaps: Optional[googlemaps.Client] = None
        self.address_parser: Optional[AddressParser] = None
        self.shipment_service: Optional[ShipmentService] = None
        self.logo_path: Optional[str] = None

        # UI Components
        self.address_search_input: Optional[QLineEdit] = None
        self.address_form: Optional[AddressForm] = None
        self.address_completer: Optional[GoogleMapsCompleter] = None
        self.shipment_controls: Optional[ShipmentControls] = None
        self.status_label: Optional[QLabel] = None
        self.status_presenter: Optional[ShippingStatusPresenter] = None
        self.address_lookup: Optional[AddressLookupCoordinator] = None
        self.shipment_flow: Optional[ShipmentFlowCoordinator] = None

        self._init_api_clients()
        self._load_logo()
        self._init_ui()
        self._init_coordinators()
        self._setup_autocomplete()

    @property
    def config(self):
        """Get the loaded configuration."""
        return self._config_manager.config

    @property
    def config_path(self) -> str:
        """Get the config file path."""
        return self._config_manager.config_path

    def _init_api_clients(self):
        """Load configuration and initialize API clients."""
        if not self._config_manager.load(parent_widget=self):
            return

        config = self._config_manager.config
        if config is None:
            return

        # Initialize Google Maps client
        self.gmaps = googlemaps.Client(key=config.googlemaps.apikey)
        self.address_parser = AddressParser(self.gmaps)

        # Initialize Shipment Service
        self.shipment_service = ShipmentService(config.easypost.apikey)

    def reload_config(self) -> bool:
        """Reload runtime configuration and recreate dependent services."""
        previous_default_weight = (
            self.config.get_default_weight() if self.config else None
        )
        if not self._config_manager.load(parent_widget=self):
            return False

        config = self._config_manager.config
        if config is None:
            return False

        self.gmaps = googlemaps.Client(key=config.googlemaps.apikey)
        self.address_parser = AddressParser(self.gmaps)
        self.shipment_service = ShipmentService(config.easypost.apikey)

        if (
            self.shipment_controls
            and previous_default_weight is not None
            and self.shipment_controls.weight_lbs == previous_default_weight
        ):
            self.shipment_controls.weight_input.setValue(config.get_default_weight())

        self._setup_autocomplete()

        return True

    def _load_logo(self):
        """Load logo image if available."""
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        if logo_path.exists():
            self.logo_path = str(logo_path)

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout()

        # Quick Lookup Section
        lookup_group = QGroupBox("Quick Lookup")
        lookup_layout = QVBoxLayout()
        address_search_layout = QHBoxLayout()
        address_search_layout.addWidget(QLabel("Address Search:"))
        self.address_search_input = QLineEdit()
        self.address_search_input.setPlaceholderText("Start typing address...")
        self.address_search_input.setToolTip("Search for addresses using Google Maps")
        address_search_layout.addWidget(self.address_search_input, 1)
        lookup_layout.addLayout(address_search_layout)
        lookup_group.setLayout(lookup_layout)
        layout.addWidget(lookup_group)

        # Recipient Address Section
        address_group = QGroupBox("Recipient Address")
        address_layout = QVBoxLayout()
        self.address_form = AddressForm()
        address_layout.addWidget(self.address_form)
        address_group.setLayout(address_layout)
        layout.addWidget(address_group)

        # Shipment Details Section
        default_weight = self.config.get_default_weight() if self.config else 1
        self.shipment_controls = ShipmentControls(default_weight=default_weight)
        layout.addWidget(self.shipment_controls)

        # Status Label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def _init_coordinators(self):
        """Create helper objects that own status and workflow behavior."""
        if (
            not self.address_search_input
            or not self.address_form
            or not self.shipment_controls
            or not self.status_label
        ):
            return

        self.status_presenter = ShippingStatusPresenter(self.status_label)
        self.address_lookup = AddressLookupCoordinator(
            parent_widget=self,
            search_input=self.address_search_input,
            address_form=self.address_form,
            status_presenter=self.status_presenter,
            get_address_parser=lambda: self.address_parser,
            get_address_completer=lambda: self.address_completer,
        )
        self.shipment_flow = ShipmentFlowCoordinator(
            parent_widget=self,
            address_search_input=self.address_search_input,
            address_form=self.address_form,
            shipment_controls=self.shipment_controls,
            status_presenter=self.status_presenter,
            get_config=lambda: self.config,
            get_shipment_service=lambda: self.shipment_service,
            get_logo_path=lambda: self.logo_path,
        )
        self.shipment_controls.create_requested.connect(self.shipment_flow.create_label)

    def _setup_autocomplete(self):
        """Set up Google Maps autocomplete on address search field."""
        if not self.gmaps or not self.address_search_input or not self.address_lookup:
            return

        if self.address_completer:
            try:
                self.address_search_input.textChanged.disconnect(
                    self.address_completer.update_completions
                )
            except (RuntimeError, TypeError):
                pass
            try:
                self.address_completer.activated.disconnect(
                    self.address_lookup.load_address
                )
            except (RuntimeError, TypeError):
                pass

        self.address_completer = setup_google_maps_autocomplete(
            self.address_search_input, self.gmaps, debounce_delay=500
        )
        self.address_completer.activated.connect(self.address_lookup.load_address)
