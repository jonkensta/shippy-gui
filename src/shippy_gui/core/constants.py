"""Application-wide constants."""

# ============================================================================
# Printing Constants
# ============================================================================

# Page dimensions in points (1 point = 1/72 inch)
# Letter size: 8.5" x 11"
PAGE_WIDTH_POINTS = 612
PAGE_HEIGHT_POINTS = 792

# Margin in points (0.25 inch = 18 points)
PAGE_MARGIN_POINTS = 18

# Default DPI for image scaling calculations
DEFAULT_PRINT_DPI = 300

# Points to inches conversion factor
POINTS_PER_INCH = 72

# Scale factor to avoid edge clipping when printing
PRINT_SCALE_FACTOR = 0.95

# Windows GDI device capability constants
# See: https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-getdevicecaps
WIN_DEVCAP_HORZRES = 8  # Horizontal resolution in pixels
WIN_DEVCAP_VERTRES = 10  # Vertical resolution in pixels
WIN_DEVCAP_PHYSICALWIDTH = 110  # Physical width in device units
WIN_DEVCAP_PHYSICALHEIGHT = 111  # Physical height in device units


# ============================================================================
# Label Constants
# ============================================================================

# Logo overlay position on shipping label (in pixels)
# Positioned in the lower-right area of a standard 4x6 shipping label
LOGO_PASTE_X = 450
LOGO_PASTE_Y = 425


# ============================================================================
# UI Constants
# ============================================================================

# Status message colors (hex)
STATUS_COLOR_INFO = "#0066CC"  # Blue
STATUS_COLOR_SUCCESS = "#008800"  # Green
STATUS_COLOR_WARNING = "#FF8800"  # Orange
STATUS_COLOR_ERROR = "#CC0000"  # Red

STATUS_COLORS = {
    "info": STATUS_COLOR_INFO,
    "success": STATUS_COLOR_SUCCESS,
    "warning": STATUS_COLOR_WARNING,
    "error": STATUS_COLOR_ERROR,
}

# Default font size
DEFAULT_FONT_SIZE = 11
FONT_SIZE_MIN = 8
FONT_SIZE_MAX = 24


# ============================================================================
# Shipping Constants
# ============================================================================

# Service Configuration
SHIPMENT_COUNTRY = "US"
SHIPMENT_CARRIER = "USPS"
SHIPMENT_SERVICE = "USPS.LIBRARYMAIL"
PARCEL_PREDEFINED_PACKAGE = "Parcel"

# Weight limits for Library Mail (in pounds)
WEIGHT_MIN_LBS = 1
WEIGHT_MAX_LBS = 70
DEFAULT_WEIGHT_LBS = 1

# Ounces per pound for weight conversion
OUNCES_PER_POUND = 16
