from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import REVOLUTIONS_PER_MINUTE, UnitOfPower, UnitOfTime

from .const import DOMAIN
from .entity import IAqualinkPumpEntity
from .models import PumpState


@dataclass(frozen=True, kw_only=True)
class PumpSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[PumpState], int | float | None]


SENSORS = (
    PumpSensorEntityDescription(
        key="speed",
        name="Pump Speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.motor_speed,
    ),
    PumpSensorEntityDescription(
        key="power",
        name="Pump Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.motor_power,
    ),
    PumpSensorEntityDescription(
        key="temperature",
        name="Pump Motor Temperature",
        # Unit isn't documented by iAquaLink, so no device_class/unit.
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: state.motor_temperature,
    ),
    PumpSensorEntityDescription(
        key="rpmtarget",
        name="Pump Target RPM",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda state: state.rpm_target,
    ),
    PumpSensorEntityDescription(
        key="customspeedrpm",
        name="Pump Custom Speed RPM",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        value_fn=lambda state: state.custom_speed_rpm,
    ),
    PumpSensorEntityDescription(
        key="customspeedtimer",
        name="Pump Custom Speed Timer",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda state: state.custom_speed_timer,
    ),
)


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(PumpSensor(coordinator, description) for description in SENSORS)


class PumpSensor(IAqualinkPumpEntity, SensorEntity):
    entity_description: PumpSensorEntityDescription

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.client.serial}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)
