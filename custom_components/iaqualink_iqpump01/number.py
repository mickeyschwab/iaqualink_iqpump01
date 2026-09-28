import logging
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
    RestoreNumber,
)
from homeassistant.const import EntityCategory, UnitOfTime
from .const import MAX_CUSTOM_SPEED_TIMER_SECONDS
from .entity import IAqualinkPumpEntity

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = config_entry.runtime_data
    async_add_entities(
        [PumpRpmTargetNumber(coordinator), PumpCustomSpeedDurationNumber(coordinator)]
    )

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
            int(value), self.coordinator.custom_speed_duration_seconds
        )


class PumpCustomSpeedDurationNumber(IAqualinkPumpEntity, RestoreNumber):
    """How long a custom speed runs before reverting to the schedule.

    Local setting (not stored on the pump): used by the RPM target number and
    by selecting custom mode. The set_custom_speed service takes its own.
    """

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = MAX_CUSTOM_SPEED_TIMER_SECONDS // 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_translation_key = "custom_speed_duration"
        self._attr_unique_id = f"{coordinator.client.serial}_custom_speed_duration"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.coordinator.custom_speed_duration_seconds = int(last.native_value) * 60

    @property
    def native_value(self):
        return self.coordinator.custom_speed_duration_seconds // 60

    async def async_set_native_value(self, value):
        self.coordinator.custom_speed_duration_seconds = int(value) * 60
        self.async_write_ha_state()
