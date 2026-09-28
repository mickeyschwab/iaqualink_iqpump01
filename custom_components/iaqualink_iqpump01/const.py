DOMAIN = "iaqualink_iqpump01"
SERVICE_MODE_REMOTE_CONTROL_ERROR = (
    "Remote control not authorized: pump is in service mode."
)

CONF_SERIAL = "serial"
# Default duration for one-tap controls (RPM number, custom mode). Stored in
# seconds; the options form edits it in minutes via CONF_CUSTOM_SPEED_DURATION_MINUTES.
CONF_CUSTOM_SPEED_TIMER_SECONDS = "custom_speed_timer_seconds"
CONF_CUSTOM_SPEED_DURATION_MINUTES = "custom_speed_duration_minutes"
CONF_UPDATE_INTERVAL_SECONDS = "update_interval_seconds"
CONF_FAST_UPDATE_INTERVAL_SECONDS = "fast_update_interval_seconds"
CONF_FAST_REFRESH_DURATION_SECONDS = "fast_refresh_duration_seconds"

DEFAULT_CUSTOM_SPEED_TIMER_SECONDS = 6 * 60 * 60
DEFAULT_UPDATE_INTERVAL_SECONDS = 60
DEFAULT_FAST_UPDATE_INTERVAL_SECONDS = 10
DEFAULT_FAST_REFRESH_DURATION_SECONDS = 3 * 60

# The iAquaLink app allows custom speed for up to 23h59.
MAX_CUSTOM_SPEED_TIMER_SECONDS = (23 * 60 + 59) * 60

SERVICE_SET_CUSTOM_SPEED = "set_custom_speed"


def option_int(options, key, default):
    """Return an integer option while tolerating legacy/string values."""
    try:
        return int(options.get(key, default))
    except (TypeError, ValueError):
        return default

