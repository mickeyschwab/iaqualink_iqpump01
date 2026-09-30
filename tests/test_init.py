"""Setup, unload, reauth, migration, diagnostics, and device registry."""
import json
from http import HTTPStatus

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iaqualink_iqpump01.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import DOMAIN, ENTRY_DATA, SERIAL, entity_id


async def test_unload(hass, entry):
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_reauth_flow(hass, entry, pump):
    pump.control_status = HTTPStatus.FORBIDDEN
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    pump.control_status = HTTPStatus.OK
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {"password": "new-pw"})
    await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-pw"


async def test_migrate_v1_removes_old_entities(hass, pump):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, version=1, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = [("switch", "pump_i2d"), ("button", "return_to_program"), ("number", "rpm_percentage"), ("sensor", "opmode")]
    for platform, suffix in old:
        registry.async_get_or_create(platform, DOMAIN, f"{SERIAL}_{suffix}", config_entry=entry)
    kept = registry.async_get_or_create("sensor", DOMAIN, f"{SERIAL}_speed", config_entry=entry, suggested_object_id="pump_speed")

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 2
    for platform, suffix in old:
        assert registry.async_get_entity_id(platform, DOMAIN, f"{SERIAL}_{suffix}") is None
    # Surviving entities keep their existing entity IDs.
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_speed") == kept.entity_id == "sensor.pump_speed"
    assert hass.states.get("sensor.pump_speed").state == "1970"


async def test_migrate_rejects_future_version(hass, pump):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, version=3, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_diagnostics_redacted(hass, entry, pump):
    diag = await async_get_config_entry_diagnostics(hass, entry)
    blob = json.dumps(diag)
    for secret in ("a@b.c", "pw", "HomeNet", SERIAL):
        assert f'"{secret}"' not in blob, secret
    assert diag["alldata"]["rpmtarget"] == "1975"
    assert diag["alldata"]["wifistatus"]["state"] == "connected"


async def test_entity_naming_and_device(hass, entry):
    mode = entity_id(hass, "select", "mode")
    assert mode == "select.iaqualink_iqpump01_pool_mode"
    st = hass.states.get(mode)
    assert st.attributes["friendly_name"] == "iAquaLink iQPump01 Pool Mode"
    assert hass.states.get(entity_id(hass, "number", "rpm_target")).attributes["friendly_name"] == "iAquaLink iQPump01 Pool Custom speed"
    device = dr.async_get(hass).async_get_device({(DOMAIN, SERIAL)})
    assert device.sw_version == "1.2"
    assert device.serial_number == SERIAL
