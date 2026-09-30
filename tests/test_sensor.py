"""Read-only entities."""
from .conftest import entity_id


async def test_sensors_and_priming(hass, entry, pump):
    assert hass.states.get(entity_id(hass, "sensor", "speed")).state == "1970"
    assert hass.states.get(entity_id(hass, "sensor", "power")).state == "350"
    temperature = hass.states.get(entity_id(hass, "sensor", "temperature"))
    assert temperature.state == "30"
    assert temperature.attributes["device_class"] == "temperature"
    assert temperature.attributes["unit_of_measurement"] == "°C"
    timer = hass.states.get(entity_id(hass, "sensor", "customspeedtimer"))
    assert timer.attributes["device_class"] == "duration"
    assert hass.states.get(entity_id(hass, "sensor", "customspeedtimer")).state == "-1"
    priming = entity_id(hass, "binary_sensor", "priming")
    assert hass.states.get(priming).state == "off"
    pump.state["primingtimer"] = "40"
    pump.state["motordata"]["speed"] = ""
    pump.state["opmode"] = "9"  # unknown mode
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(priming).state == "on"
    assert hass.states.get(priming).attributes["priming_timer"] == 40
    assert hass.states.get(entity_id(hass, "sensor", "speed")).state == "unknown"
    assert hass.states.get(entity_id(hass, "select", "mode")).state == "unknown"
