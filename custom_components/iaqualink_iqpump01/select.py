import logging

from homeassistant.components.select import SelectEntity

from .const import DOMAIN
from .entity import IAqualinkPumpEntity
from .models import WRITABLE_OPMODES, OpMode

_LOGGER = logging.getLogger(__name__)

MODE_OPTIONS = {
    OpMode.AUTO: "auto",
    OpMode.CUSTOM: "custom",
    OpMode.OFF: "off",
    OpMode.QUICK_CLEAN: "quick_clean",
    OpMode.TIMED_RUN: "timed_run",
    OpMode.TIMED_STOP: "timed_stop",
    OpMode.SERVICE: "service",
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([PumpModeSelect(coordinator)])


class PumpModeSelect(IAqualinkPumpEntity, SelectEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_name = "Pump Mode"
        self._attr_unique_id = f"{client.serial}_mode"
        self._attr_icon = "mdi:pump"

    @property
    def options(self):
        options = [MODE_OPTIONS[mode] for mode in WRITABLE_OPMODES]
        # Read-only modes are listed only while the pump is in them.
        current = self.coordinator.data.opmode
        if current is not None and current not in WRITABLE_OPMODES:
            options.append(MODE_OPTIONS[current])
        return options

    @property
    def current_option(self):
        current = self.coordinator.data.opmode
        return MODE_OPTIONS.get(current) if current is not None else None

    async def async_select_option(self, option):
        opmode = next(mode for mode, name in MODE_OPTIONS.items() if name == option)
        await self.coordinator.async_set_opmode(opmode)
