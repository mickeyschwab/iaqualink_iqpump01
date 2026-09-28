import asyncio
import logging
import voluptuous as vol
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import CONF_SERIAL, DOMAIN, SERVICE_SET_CUSTOM_SPEED
from .api import (
    IAqualinkAuthError,
    IAqualinkClient,
    IAqualinkConnectionError,
    IAqualinkNoDeviceError,
)
from .coordinator import IAqualinkConfigEntry, IAqualinkPumpCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["select", "number", "sensor", "binary_sensor"]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_CUSTOM_SPEED_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("rpm"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Required("duration"): vol.All(cv.time_period, cv.positive_timedelta),
    }
)

async def async_setup(hass: HomeAssistant, config: dict):
    async def async_handle_set_custom_speed(call: ServiceCall):
        duration_seconds = int(call.data["duration"].total_seconds())
        coordinators = []
        for device_id in call.data[ATTR_DEVICE_ID]:
            coordinator = IAqualinkPumpCoordinator.async_get_by_device_id(hass, device_id)
            if coordinator is None:
                raise HomeAssistantError(
                    f"Device {device_id} is not an iAquaLink iQPump01 pump"
                )
            coordinators.append(coordinator)

        await asyncio.gather(
            *(
                coordinator.async_set_custom_speed_rpm(call.data["rpm"], duration_seconds)
                for coordinator in coordinators
            )
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CUSTOM_SPEED,
        async_handle_set_custom_speed,
        schema=SET_CUSTOM_SPEED_SCHEMA,
    )
    return True

# Entities removed in 2.0.0, as (platform, unique_id suffix after the serial).
REMOVED_ENTITIES = (
    ("switch", "_pump_i2d"),
    ("button", "_return_to_program"),
    ("number", "_rpm_percentage"),
    ("sensor", "_opmode"),
)


async def async_migrate_entry(hass: HomeAssistant, entry: IAqualinkConfigEntry):
    if entry.version > 2:
        # Downgrade from a newer, unknown schema.
        return False

    if entry.version == 1:
        # 1.x -> 2.0.0: drop registry entries for entities that no longer
        # exist, so they don't linger as "unavailable".
        registry = er.async_get(hass)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if any(
                reg_entry.domain == platform and reg_entry.unique_id.endswith(suffix)
                for platform, suffix in REMOVED_ENTITIES
            ):
                _LOGGER.info("Removing entity %s (removed in 2.0.0)", reg_entry.entity_id)
                registry.async_remove(reg_entry.entity_id)
        hass.config_entries.async_update_entry(entry, version=2)

    return True


async def async_options_update_listener(hass: HomeAssistant, entry: IAqualinkConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: IAqualinkConfigEntry):
    client = IAqualinkClient(
        async_get_clientsession(hass),
        entry.data["email"],
        entry.data["password"],
        entry.data.get(CONF_SERIAL),
    )
    try:
        await client.login()
    except IAqualinkAuthError as err:
        raise ConfigEntryAuthFailed("iAquaLink authentication failed") from err
    except IAqualinkNoDeviceError as err:
        raise ConfigEntryNotReady("No iQPump01 controller found in iAquaLink account") from err
    except IAqualinkConnectionError as err:
        raise ConfigEntryNotReady("Unable to connect to iAquaLink") from err

    update_kwargs = {}
    if entry.unique_id is None:
        update_kwargs["unique_id"] = client.serial
    if entry.data.get(CONF_SERIAL) != client.serial:
        data = dict(entry.data)
        data[CONF_SERIAL] = client.serial
        update_kwargs["data"] = data
    if update_kwargs:
        hass.config_entries.async_update_entry(entry, **update_kwargs)

    coordinator = IAqualinkPumpCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(async_options_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: IAqualinkConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry.runtime_data.async_shutdown()
    return unload_ok
