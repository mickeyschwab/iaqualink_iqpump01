import logging
from homeassistant.components.number import NumberEntity
from homeassistant.const import REVOLUTIONS_PER_MINUTE
from .entity import IAqualinkPumpEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = config_entry.runtime_data
    async_add_entities([PumpCustomSpeedNumber(coordinator)])

class PumpCustomSpeedNumber(IAqualinkPumpEntity, NumberEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_translation_key = "custom_speed"
        # Kept from when this showed rpmtarget, so entity IDs don't change.
        self._attr_unique_id = f"{client.serial}_rpm_target"
        # The pump only accepts RPM targets in increments of 25.
        self._attr_native_step = 25
        self._attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE

    @property
    def native_min_value(self):
        return self.coordinator.data.rpm_min

    @property
    def native_max_value(self):
        return self.coordinator.data.rpm_max

    @property
    def native_value(self):
        # The saved custom speed, not rpmtarget: in auto mode rpmtarget follows
        # the schedule, and "Actual speed" already shows what the motor does.
        return self.coordinator.data.custom_speed_rpm

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_custom_speed_rpm(
            int(value), self.coordinator.default_custom_speed_duration()
        )

