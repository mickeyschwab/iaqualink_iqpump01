import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    IAqualinkAuthError,
    IAqualinkClient,
    IAqualinkConnectionError,
    IAqualinkError,
)
from .const import (
    CONF_CUSTOM_SPEED_TIMER_SECONDS,
    CONF_FAST_REFRESH_DURATION_SECONDS,
    CONF_FAST_UPDATE_INTERVAL_SECONDS,
    CONF_UPDATE_INTERVAL_SECONDS,
    DEFAULT_CUSTOM_SPEED_TIMER_SECONDS,
    DEFAULT_FAST_REFRESH_DURATION_SECONDS,
    DEFAULT_FAST_UPDATE_INTERVAL_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    MAX_CUSTOM_SPEED_TIMER_SECONDS,
    SERVICE_MODE_REMOTE_CONTROL_ERROR,
    option_int,
)
from .models import WRITABLE_OPMODES, OpMode, PumpState

_LOGGER = logging.getLogger(__name__)

class IAqualinkPumpCoordinator(DataUpdateCoordinator[PumpState]):
    """Coordinate iAquaLink pump polling for all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: IAqualinkClient,
        config_entry: ConfigEntry,
    ) -> None:
        self.config_entry = config_entry
        self.default_update_interval = timedelta(
            seconds=option_int(
                config_entry.options,
                CONF_UPDATE_INTERVAL_SECONDS,
                DEFAULT_UPDATE_INTERVAL_SECONDS,
            )
        )
        self.fast_update_interval = timedelta(
            seconds=option_int(
                config_entry.options,
                CONF_FAST_UPDATE_INTERVAL_SECONDS,
                DEFAULT_FAST_UPDATE_INTERVAL_SECONDS,
            )
        )
        self.fast_refresh_duration = timedelta(
            seconds=option_int(
                config_entry.options,
                CONF_FAST_REFRESH_DURATION_SECONDS,
                DEFAULT_FAST_REFRESH_DURATION_SECONDS,
            )
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=self.default_update_interval,
        )
        self.client = client
        self._fast_refresh_unsub = None
        # Owned by the custom speed duration number entity, which restores it.
        self.custom_speed_duration_seconds = option_int(
            config_entry.options,
            CONF_CUSTOM_SPEED_TIMER_SECONDS,
            DEFAULT_CUSTOM_SPEED_TIMER_SECONDS,
        )

    async def _async_update_data(self):
        try:
            return PumpState.from_alldata(await self.client.refresh_data())
        except IAqualinkAuthError as err:
            raise ConfigEntryAuthFailed("iAquaLink authentication failed") from err
        except IAqualinkConnectionError as err:
            raise UpdateFailed(f"Network/HTTP error communicating with iAquaLink: {err}") from err
        except IAqualinkError as err:
            raise UpdateFailed(f"Unexpected iAquaLink error: {err}") from err

    @callback
    def enable_fast_refresh(self) -> None:
        self.update_interval = self.fast_update_interval
        if self._fast_refresh_unsub is not None:
            self._fast_refresh_unsub()
        self._fast_refresh_unsub = async_call_later(
            self.hass,
            self.fast_refresh_duration.total_seconds(),
            self._disable_fast_refresh,
        )
        _LOGGER.debug(
            "[enable_fast_refresh] Using %ss polling for %ss after speed change.",
            int(self.fast_update_interval.total_seconds()),
            int(self.fast_refresh_duration.total_seconds()),
        )

    @callback
    def _disable_fast_refresh(self, *_):
        self.update_interval = self.default_update_interval
        self._fast_refresh_unsub = None
        _LOGGER.debug(
            "[disable_fast_refresh] Restored %ss polling.",
            int(self.default_update_interval.total_seconds()),
        )

    @callback
    def async_shutdown(self) -> None:
        if self._fast_refresh_unsub is not None:
            self._fast_refresh_unsub()
            self._fast_refresh_unsub = None

    @staticmethod
    def async_get_by_device_id(hass: HomeAssistant, device_id: str) -> "IAqualinkPumpCoordinator | None":
        """Resolve a Home Assistant device_id to its IAqualinkPumpCoordinator, if any."""
        device = dr.async_get(hass).async_get(device_id)
        if device is None:
            return None
        domain_entries = hass.data.get(DOMAIN, {})
        entry_id = next(iter(device.config_entries & domain_entries.keys()), None)
        return domain_entries.get(entry_id)

    def raise_if_service_mode(self, action) -> None:
        if self.data is None or self.data.opmode is not OpMode.SERVICE:
            return
        _LOGGER.warning("%s ignored: pump in service mode", action)
        raise HomeAssistantError(SERVICE_MODE_REMOTE_CONTROL_ERROR)

    async def async_set_opmode(self, opmode: OpMode) -> None:
        """Switch operating mode (used by the mode select)."""
        if opmode not in WRITABLE_OPMODES:
            raise HomeAssistantError(
                f"Mode {opmode.name.lower()} can't be set remotely."
            )
        if opmode is OpMode.CUSTOM:
            # opmode=1 alone may be ignored; resume the pump's saved custom
            # speed through the full custom-speed sequence instead.
            rpm = self.data.custom_speed_rpm or self.data.rpm_target
            if rpm is None:
                raise HomeAssistantError("Pump has no saved custom speed to resume.")
            await self.async_set_custom_speed_rpm(
                rpm, self.custom_speed_duration_seconds
            )
            return

        self.raise_if_service_mode("Set mode command")
        try:
            await self.client.set_opmode(opmode)
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to set pump mode: {err}") from err

        self.enable_fast_refresh()
        await self.async_request_refresh()

    async def async_set_custom_speed_rpm(self, rpm, duration_seconds) -> None:
        """Set a custom speed via raw RPM (used by the number entity and service)."""
        rpm_min, rpm_max = self.data.rpm_min, self.data.rpm_max
        if not rpm_min <= rpm <= rpm_max:
            raise HomeAssistantError(
                f"RPM must be between {rpm_min} and {rpm_max} for this pump."
            )
        await self._async_write_custom_speed(rpm, duration_seconds)

    async def _async_write_custom_speed(self, rpm, duration_seconds) -> None:
        self.raise_if_service_mode("Set custom speed command")

        if not 1 <= duration_seconds <= MAX_CUSTOM_SPEED_TIMER_SECONDS:
            raise HomeAssistantError(
                "Duration must be between 1 second and "
                f"{MAX_CUSTOM_SPEED_TIMER_SECONDS} seconds (23h59)."
            )

        _LOGGER.debug(
            "[_async_write_custom_speed] %s RPM for %ss",
            rpm,
            duration_seconds,
        )

        try:
            await self.client.set_custom_speed(rpm, duration_seconds)
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to set pump speed: {err}") from err

        self.enable_fast_refresh()
        await self.async_request_refresh()
