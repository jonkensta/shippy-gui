"""Unified shipping tab with manual address entry."""

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
from shippy_gui.dialogs import show_config_error, show_error
from shippy_gui.shipping_coordinators import (
    AddressLookupCoordinator,
    ShipmentFlowCoordinator,
    ShippingServices,
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

    # pylint: disable=too-many-instance-attributes  # Widgets plus their coordinators.

    def __init__(self, config_path: Optional[str] = None, parent=None):
        """Initialize the shipping tab."""
        super().__init__(parent)
        self._config_manager = ConfigManager(config_path)
        self._services = ShippingServices(logo_path=self._resolve_logo_path())

        self._load_config()
        self._build_services()
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

    @property
    def gmaps(self) -> Optional[googlemaps.Client]:
        """Get the active Google Maps client."""
        return self._services.gmaps

    @property
    def address_parser(self) -> Optional[AddressParser]:
        """Get the active address parser."""
        return self._services.address_parser

    @property
    def shipment_service(self) -> Optional[ShipmentService]:
        """Get the active shipment service."""
        return self._services.shipment_service

    @property
    def address_completer(self) -> Optional[GoogleMapsCompleter]:
        """Get the active address autocompleter."""
        return self._services.address_completer

    @property
    def logo_path(self) -> Optional[str]:
        """Get the resolved logo overlay path."""
        return self._services.logo_path

    def _load_config(self) -> bool:
        """Load configuration, presenting any failure."""
        result = self._config_manager.load()
        if not result.ok:
            show_config_error(self, result)
            return False
        return True

    def _build_services(self) -> bool:
        """(Re)create the API clients that depend on configuration.

        Everything is constructed before anything is published to the shared
        holder, so a failure part way through cannot leave the coordinators
        holding a new config alongside a stale shipment service.
        """
        config = self._config_manager.config
        if config is None:
            return False

        try:
            gmaps = googlemaps.Client(key=config.googlemaps.apikey)
            address_parser = AddressParser(gmaps)
            shipment_service = ShipmentService(config.easypost.apikey, config.parcel)
        except Exception as error:  # pylint: disable=broad-exception-caught
            show_error(
                self,
                "Service Error",
                f"Could not initialize API clients:\n\n{error}",
            )
            return False

        self._services.config = config
        self._services.gmaps = gmaps
        self._services.address_parser = address_parser
        self._services.shipment_service = shipment_service
        return True

    def reload_config(self) -> bool:
        """Reload runtime configuration and recreate dependent services.

        The coordinators are not rebuilt: they read through the shared
        ShippingServices holder, which is rewritten in place here.
        """
        previous_default_weight = (
            self.config.get_default_weight() if self.config else None
        )
        if not self._load_config():
            return False
        if not self._build_services():
            return False

        config = self._config_manager.config
        if (
            config is not None
            and previous_default_weight is not None
            and self.shipment_controls.weight_lbs == previous_default_weight
        ):
            self.shipment_controls.weight_input.setValue(config.get_default_weight())

        self._setup_autocomplete()
        return True

    @staticmethod
    def _resolve_logo_path() -> Optional[str]:
        """Resolve the bundled logo image path if it is available."""
        logo_path = Path(__file__).parent.parent / "assets" / "logo.jpg"
        return str(logo_path) if logo_path.exists() else None

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
        self.status_presenter = ShippingStatusPresenter(self.status_label)
        self.address_lookup = AddressLookupCoordinator(
            parent_widget=self,
            search_input=self.address_search_input,
            address_form=self.address_form,
            status_presenter=self.status_presenter,
            services=self._services,
        )
        self.shipment_flow = ShipmentFlowCoordinator(
            parent_widget=self,
            address_search_input=self.address_search_input,
            address_form=self.address_form,
            shipment_controls=self.shipment_controls,
            status_presenter=self.status_presenter,
            services=self._services,
        )
        self.shipment_controls.create_requested.connect(self.shipment_flow.create_label)

    def _setup_autocomplete(self):
        """Set up Google Maps autocomplete on address search field."""
        if not self._services.gmaps:
            return

        completer = self._services.address_completer
        if completer:
            try:
                self.address_search_input.textChanged.disconnect(
                    completer.update_completions
                )
            except (RuntimeError, TypeError):
                pass
            try:
                completer.activated.disconnect(self.address_lookup.load_address)
            except (RuntimeError, TypeError):
                pass

        self._services.address_completer = setup_google_maps_autocomplete(
            self.address_search_input, self._services.gmaps, debounce_delay=500
        )
        self._services.address_completer.activated.connect(
            self.address_lookup.load_address
        )
