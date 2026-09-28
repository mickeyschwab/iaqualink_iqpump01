import logging
from homeassistant.components.number import NumberEntity
from .entity import IAqualinkPumpEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = config_entry.runtime_data
    async_add_entities([PumpRpmTargetNumber(coordinator)])

class PumpRpmTargetNumber(IAqualinkPumpEntity, NumberEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_translation_key = "rpm_target"
        self._attr_unique_id = f"{client.serial}_rpm_target"
        # The pump only accepts RPM targets in increments of 25.
        self._attr_native_step = 25
        self._attr_native_unit_of_measurement = "rpm"

    @property
    def native_min_value(self):
        return self.coordinator.data.rpm_min

    @property
    def native_max_value(self):
        return self.coordinator.data.rpm_max

    @property
    def native_value(self):
        return self.coordinator.data.rpm_target

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_custom_speed_rpm(
            int(value), self.coordinator.default_custom_speed_duration()
        )

