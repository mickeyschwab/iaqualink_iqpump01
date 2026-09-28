from homeassistant.core import HomeAssistant

from .api import IAqualinkClient
from .coordinator import IAqualinkConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: IAqualinkConfigEntry
) -> dict:
    """Return redacted pump state for troubleshooting.

    Uses the same redaction as debug logging (emails, tokens, SSIDs, serials,
    addresses, ...) so a downloaded diagnostics file is safe to share.
    """
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": IAqualinkClient.redact(dict(entry.data)),
            "options": dict(entry.options),
        },
        "device": IAqualinkClient.redact(coordinator.client.device or {}),
        "alldata": IAqualinkClient.redact(coordinator.data.raw),
        "update_interval_seconds": coordinator.update_interval.total_seconds(),
    }
