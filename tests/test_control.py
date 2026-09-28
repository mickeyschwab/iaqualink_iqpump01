"""Speed, duration, and mode writes."""
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from .conftest import DOMAIN, ENTRY_DATA, SERIAL, entity_id


async def test_setup_and_rpm_number(hass, entry, pump):
    assert entry.state is ConfigEntryState.LOADED
    number = entity_id(hass, "number", "rpm_target")
    st = hass.states.get(number)
    assert st.state == "1975"
    assert st.attributes["min"] == 600
    assert st.attributes["max"] == 3450
    assert st.attributes["step"] == 25

    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 2250}, blocking=True)
    assert pump.writes == [("opmode", "1"), ("customspeedrpm", "2250"), ("customspeedtimer", "21600")]
    assert hass.states.get(number).state == "2250"


async def test_service_rpm_and_duration(hass, entry, pump):
    device = dr.async_get(hass).async_get_device({(DOMAIN, SERIAL)})
    await hass.services.async_call(
        DOMAIN, "set_custom_speed",
        {"device_id": device.id, "rpm": 3010, "duration": {"hours": 1, "minutes": 30}},
        blocking=True,
    )
    assert pump.writes == [("opmode", "1"), ("customspeedrpm", "3000"), ("customspeedtimer", "5400")]
    # Pre-2.0 YAML used `target: device_id:`; HA merges target into the data.
    pump.writes.clear()
    await hass.services.async_call(
        DOMAIN, "set_custom_speed", {"rpm": 1500, "duration": {"minutes": 30}},
        blocking=True, target={"device_id": device.id},
    )
    assert pump.writes == [("opmode", "1"), ("customspeedrpm", "1500"), ("customspeedtimer", "1800")]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "set_custom_speed",
            {"device_id": device.id, "rpm": 5000, "duration": {"hours": 1}}, blocking=True,
        )


async def test_ignored_write_raises(hass, entry, pump):
    pump.ignore.add("customspeedrpm")
    number = entity_id(hass, "number", "rpm_target")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 2500}, blocking=True)


async def test_service_mode_blocks_writes(hass, entry, pump):
    pump.state["opmode"] = "7"
    await entry.runtime_data.async_refresh()
    number = entity_id(hass, "number", "rpm_target")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 2500}, blocking=True)
    assert pump.writes == []


async def test_duration_entity_drives_writes(hass, entry, pump):
    duration = entity_id(hass, "number", "custom_speed_duration")
    assert hass.states.get(duration).state == "360"
    await hass.services.async_call("number", "set_value", {"entity_id": duration, "value": 90}, blocking=True)
    assert hass.states.get(duration).state == "90"
    assert pump.writes == []  # local setting, no pump write
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id(hass, "number", "rpm_target"), "value": 1500}, blocking=True
    )
    assert pump.writes[-1] == ("customspeedtimer", "5400")


async def test_duration_restored(hass, pump):
    mock_restore_cache_with_extra_data(
        hass,
        [(State("number.iaqualink_iqpump01_pool_pump_custom_speed_duration", "45"),
          {"native_value": 45, "native_min_value": 1, "native_max_value": 1439, "native_step": 1, "native_unit_of_measurement": "min"})],
    )
    er.async_get(hass).async_get_or_create(
        "number", DOMAIN, f"{SERIAL}_custom_speed_duration",
        suggested_object_id="iaqualink_iqpump01_pool_pump_custom_speed_duration",
    )
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, version=2, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id(hass, "number", "custom_speed_duration")).state == "45"
    assert entry.runtime_data.custom_speed_duration_seconds == 2700


async def test_mode_select(hass, entry, pump):
    mode = entity_id(hass, "select", "mode")
    st = hass.states.get(mode)
    assert st.state == "auto"
    assert st.attributes["options"] == ["auto", "custom", "off"]
    assert hass.states.get(entity_id(hass, "binary_sensor", "running")).state == "on"

    await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "off"}, blocking=True)
    assert pump.writes == [("opmode", "2")]
    assert hass.states.get(mode).state == "off"

    pump.writes.clear()
    # custom resumes the saved custom speed via the full sequence
    await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "custom"}, blocking=True)
    assert pump.writes == [("opmode", "1"), ("customspeedrpm", "2000"), ("customspeedtimer", "21600")]


async def test_read_only_mode_listed_only_when_active(hass, entry, pump):
    pump.state["opmode"] = "3"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    mode = entity_id(hass, "select", "mode")
    st = hass.states.get(mode)
    assert st.state == "quick_clean"
    assert st.attributes["options"] == ["auto", "custom", "off", "quick_clean"]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "quick_clean"}, blocking=True)
    assert pump.writes == []


async def test_service_mode_select(hass, entry, pump):
    pump.state["opmode"] = "7"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    mode = entity_id(hass, "select", "mode")
    assert hass.states.get(mode).state == "service"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "auto"}, blocking=True)
    assert pump.writes == []
