"""Application-wide constants."""

# ============================================================================
# Printing Constants
# ============================================================================

# Page layout, scaling and platform details are owned by ibp-printing.

# Spooler job name for quick prints (the tracking code is appended when known).
PRINT_JOB_NAME = "Shipping Label"

# How long a quick print follows the spooled job before reporting success.
# Tracking only adds detail to the printer logs: the call returns as soon as the
# job completes or leaves the queue, and an errored or timed-out job never
# triggers a refund (the label may still print once the printer is fixed).
# Kept above ibp-printing's 10 s error grace period so a stuck job is logged
# as an error rather than a timeout.
PRINT_TRACK_TIMEOUT_S = 15.0


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

# Logging defaults
DEFAULT_LOG_FILENAME = "shippy.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


# ============================================================================
# Shipping Constants
# ============================================================================

# Service Configuration
SHIPMENT_COUNTRY = "US"
SHIPMENT_CARRIER = "USPS"
SHIPMENT_SERVICE = "USPS.LIBRARYMAIL"
PARCEL_PREDEFINED_PACKAGE = "Parcel"

# Default declared parcel dimensions in inches. USPS requires all three
# dimensions for the "Parcel" container type. Library Mail is priced by
# weight alone, so these just need to be large enough for any book package
# while staying under the USPS nonstandard-size surcharge thresholds
# (22 inches per side, 2 cubic feet).
DEFAULT_PARCEL_LENGTH_IN = 20.0
DEFAULT_PARCEL_WIDTH_IN = 14.0
DEFAULT_PARCEL_HEIGHT_IN = 10.0

# Weight limits for Library Mail (in pounds)
WEIGHT_MIN_LBS = 1
WEIGHT_MAX_LBS = 70
DEFAULT_WEIGHT_LBS = 3

# Ounces per pound for weight conversion
OUNCES_PER_POUND = 16
