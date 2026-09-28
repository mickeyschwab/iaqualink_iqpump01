"""Fixtures: a fake iQPump01 behind a mocked iAquaLink cloud API."""
from http import HTTPStatus
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

import custom_components

# pytest-homeassistant-custom-component ships its own `custom_components`
# package, which shadows this repo's; make ours discoverable too.
custom_components.__path__.append(str(Path(__file__).parent.parent / "custom_components"))

DOMAIN = "iaqualink_iqpump01"
SERIAL = "SN123456"
ENTRY_DATA = {"email": "a@b.c", "password": "pw", "serial": SERIAL}
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
DEVICES_URL = "https://r-api.iaqualink.net/devices.json"
CONTROL_URL = f"https://r-api.iaqualink.net/v2/devices/{SERIAL}/control.json"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def entity_id(hass, platform, unique_suffix):
    """Look up an entity ID by its unique_id suffix (after the serial)."""
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{SERIAL}_{unique_suffix}"
    )


class FakePump:
    """In-memory iQPump01 that answers the control endpoint like iAquaLink.

    Writes are recorded in `writes` and echoed back. Commands listed in
    `ignore` echo the old value instead (iAquaLink silently ignoring a write),
    and `control_status` forces an HTTP error.
    """

    def __init__(self):
        self.state = {
            "serialnumber": SERIAL,
            "opmode": "0",
            "runstate": "on",
            "rpmtarget": "1975",
            "customspeedrpm": "2000",
            "customspeedtimer": "-1",
            "globalrpmmin": "600",
            "globalrpmmax": "3450",
            "primingtimer": "-1",
            "primingperiod": "60",
            "primingrpm": "2000",
            "fwversion": "1.2",
            "localtime": "12:00",
            "motordata": {"speed": "1970", "power": "350", "temperature": "30", "productid": "x"},
            "wifistatus": {"ssid": "HomeNet", "state": "connected"},
        }
        self.writes = []
        self.ignore = set()
        self.control_status = HTTPStatus.OK

    async def control(self, method, url, data):
        if self.control_status != HTTPStatus.OK:
            return AiohttpClientMockResponse(method, url, status=self.control_status)
        command = data["command"]
        if command == "/alldata/read":
            return AiohttpClientMockResponse(method, url, json={"alldata": self.state})
        key = command.strip("/").split("/")[0]
        value = data["params"].removeprefix("value=")
        self.writes.append((key, value))
        if key not in self.ignore:
            self.state[key] = value
            if key == "customspeedrpm":
                self.state["rpmtarget"] = value
        return AiohttpClientMockResponse(method, url, json={key: {"value": self.state[key]}})


@pytest.fixture
def pump(aioclient_mock):
    pump = FakePump()
    aioclient_mock.post(
        LOGIN_URL,
        json={
            "authentication_token": "tok",
            "session_id": "sess",
            "id": 42,
            "userPoolOAuth": {"IdToken": "idtok"},
        },
    )
    aioclient_mock.get(
        DEVICES_URL,
        json=[{"device_type": "i2d", "serial_number": SERIAL, "name": "Pool"}],
    )
    aioclient_mock.post(CONTROL_URL, side_effect=pump.control)
    return pump


@pytest.fixture
async def entry(hass, pump):
    """A loaded config entry for the fake pump."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, version=2, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
