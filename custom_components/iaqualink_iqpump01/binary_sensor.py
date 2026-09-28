import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from .const import DOMAIN
from .entity import IAqualinkPumpEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [PumpRunningBinarySensor(coordinator), PumpPrimingBinarySensor(coordinator)]
    )


class PumpRunningBinarySensor(IAqualinkPumpEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Pump Running"
        self._attr_unique_id = f"{coordinator.client.serial}_running"

    @property
    def is_on(self):
        return self.coordinator.data.running


class PumpPrimingBinarySensor(IAqualinkPumpEntity, BinarySensorEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_name = "Pump Priming"
        self._attr_unique_id = f"{client.serial}_priming"
        self._attr_icon = "mdi:timer-sand"

    @property
    def is_on(self):
        return self.coordinator.data.is_priming

    @property
    def extra_state_attributes(self):
        state = self.coordinator.data
        return {
            "priming_timer": state.priming_timer,
            "priming_period": state.priming_period,
            "priming_rpm": state.priming_rpm,
        }
