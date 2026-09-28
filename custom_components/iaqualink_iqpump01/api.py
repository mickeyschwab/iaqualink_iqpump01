import asyncio
import logging
import json

import aiohttp

from .models import OpMode

_LOGGER = logging.getLogger(__name__)
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)
REDACTED = "<redacted>"
CONTROL_USER_AGENT = "iAqualink/934 CFNetwork/3826.500.111.2.2 Darwin/24.4.0"
CONTROL_ACCEPT_LANGUAGE = "fr-CA,fr;q=0.9"
# The controller only accepts RPM targets in increments of 25.
RPM_STEP = 25
SENSITIVE_LOG_KEYS = {
    "accesskeyid",
    "address",
    "address_1",
    "address_2",
    "authentication_token",
    "authorization",
    "city",
    "cookie",
    "email",
    "first_name",
    "id",
    "identityid",
    "idtoken",
    "last_name",
    "password",
    "phone",
    "postal_code",
    "refreshtoken",
    "secretkey",
    "session_id",
    "sessiontoken",
    "ssid",
    "state",
    "username",
}
SENSITIVE_LOG_KEY_PARTS = (
    "credential",
    "secret",
    "session",
    "token",
)

class IAqualinkError(Exception):
    """Base iAquaLink API error."""


class IAqualinkAuthError(IAqualinkError):
    """Authentication or authorization failed."""


class IAqualinkConnectionError(IAqualinkError):
    """Unable to communicate with iAquaLink."""


class IAqualinkNoDeviceError(IAqualinkError):
    """No supported pump was found in the account."""


class IAqualinkCommandError(IAqualinkError):
    """iAquaLink rejected or ignored a command."""


class IAqualinkClient:
    def __init__(self, session: aiohttp.ClientSession, email, password, serial=None):
        self._session = session
        self.email = email
        self.password = password
        self.apikey = "EOOEMOW4YR6QNB07"
        self.auth_token = None
        self.session_id = None
        self.user_id = None
        self.id_token = None
        self.serial = str(serial) if serial is not None else None
        self.devices = []
        self.device = None
        self.data = {}
        # Serializes command sequences so two multi-write operations on the same
        # pump can't interleave.
        self._command_lock = asyncio.Lock()

    @staticmethod
    def _safe_url(url):
        return url.split("?", 1)[0]

    @staticmethod
    def _mask_email(value):
        if not isinstance(value, str) or "@" not in value:
            return REDACTED
        local, domain = value.split("@", 1)
        if len(local) <= 2:
            masked_local = local[:1] + "***"
        else:
            masked_local = local[:2] + "***" + local[-1:]
        return f"{masked_local}@{domain}"

    @staticmethod
    def _mask_suffix(value, visible=4):
        text = str(value)
        if len(text) <= visible:
            return REDACTED
        return f"***{text[-visible:]}"

    @classmethod
    def _redact_value(cls, key, value):
        normalized_key = str(key).lower()
        if normalized_key == "wifistatus" and isinstance(value, dict):
            return {
                "state": value.get("state"),
                "ssid": REDACTED,
            }
        if normalized_key == "email":
            return cls._mask_email(value)
        if normalized_key in {"serial_number", "serialnumber"}:
            return cls._mask_suffix(value)
        if normalized_key in SENSITIVE_LOG_KEYS or any(
            part in normalized_key for part in SENSITIVE_LOG_KEY_PARTS
        ):
            return REDACTED
        return cls._redact_for_log(value)

    @classmethod
    def _redact_for_log(cls, value):
        if isinstance(value, dict):
            return {key: cls._redact_value(key, item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact_for_log(item) for item in value]
        return value

    def _log_response(self, label, status, text):
        try:
            body = self._redact_for_log(json.loads(text))
        except ValueError:
            _LOGGER.debug(
                "[%s] Response status=%s body=<non-json, %s bytes>",
                label,
                status,
                len(text or ""),
            )
            return

        _LOGGER.debug(
            "[%s] Response status=%s body=%s",
            label,
            status,
            json.dumps(body, sort_keys=True),
        )

    @staticmethod
    def _raise_for_status(status, context):
        if status < 400:
            return
        if status in (401, 403):
            raise IAqualinkAuthError(
                f"iAquaLink authentication failed during {context}"
            )
        raise IAqualinkConnectionError(
            f"iAquaLink returned HTTP {status} during {context}"
        )

    async def _request(self, method, url, **kwargs):
        """Perform a request and return (status, body text)."""
        try:
            async with self._session.request(
                method, url, timeout=REQUEST_TIMEOUT, **kwargs
            ) as response:
                return response.status, await response.text()
        except TimeoutError:
            _LOGGER.warning(
                "[_request] iAquaLink %s request timed out after %ss: %s",
                method.upper(),
                REQUEST_TIMEOUT.total,
                self._safe_url(url),
            )
            raise IAqualinkConnectionError(
                f"iAquaLink {method.upper()} request timed out"
            ) from None
        except aiohttp.ClientError as err:
            _LOGGER.warning(
                "[_request] iAquaLink %s request failed for %s: %s",
                method.upper(),
                self._safe_url(url),
                err.__class__.__name__,
            )
            raise IAqualinkConnectionError(
                f"iAquaLink {method.upper()} request failed"
            ) from err

    @staticmethod
    def _parse_json(text, context):
        try:
            return json.loads(text)
        except ValueError as err:
            raise IAqualinkConnectionError(
                f"iAquaLink returned invalid JSON during {context}"
            ) from err

    def _control_url(self):
        return f"https://r-api.iaqualink.net/v2/devices/{self.serial}/control.json?"

    def _control_headers(self):
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "cookie": f"session_id={self.session_id}; authentication_token={self.auth_token}",
            "authorization": self.id_token,
            "api_key": self.apikey,
            "user-agent": CONTROL_USER_AGENT,
            "accept-language": CONTROL_ACCEPT_LANGUAGE,
        }

    async def _post_control(self, payload, context):
        """POST to the control endpoint, re-authenticating once on 401."""
        control_url = self._control_url()
        status, text = await self._request(
            "post", control_url, headers=self._control_headers(), json=payload
        )
        if status == 401:
            _LOGGER.warning("[%s] Token expired, reauthenticating...", context)
            await self.login()
            status, text = await self._request(
                "post", control_url, headers=self._control_headers(), json=payload
            )
        self._log_response(context, status, text)
        self._raise_for_status(status, context)
        return self._parse_json(text, context)

    async def login(self):
        _LOGGER.debug(
            "[login] Logging in with email: %s", self._mask_email(self.email)
        )
        login_url = "https://prod.zodiac-io.com/users/v1/login"
        payload = {
            "email": self.email,
            "password": self.password,
            "apikey": self.apikey
        }
        status, text = await self._request("post", login_url, json=payload)
        self._log_response("login", status, text)
        self._raise_for_status(status, "login")

        data = self._parse_json(text, "login")
        try:
            self.auth_token = data["authentication_token"]
            self.session_id = data["session_id"]
            self.user_id = data["id"]
            self.id_token = data["userPoolOAuth"]["IdToken"]
        except KeyError as err:
            raise IAqualinkAuthError("iAquaLink login response is missing auth data") from err

        device_url = "https://r-api.iaqualink.net/devices.json"
        status, text = await self._request(
            "get",
            device_url,
            params={
                "authentication_token": self.auth_token,
                "user_id": self.user_id,
                "api_key": self.apikey,
            },
        )
        self._log_response("device_url", status, text)
        self._raise_for_status(status, "devices list")

        devices_payload = self._parse_json(text, "devices list")
        if isinstance(devices_payload, dict):
            devices_payload = devices_payload.get("devices", [])

        self.devices = [
            device
            for device in devices_payload
            if (
                isinstance(device, dict)
                and device.get("device_type") == "i2d"
                and device.get("serial_number")
            )
        ]

        if not self.devices:
            raise IAqualinkNoDeviceError(
                "No iQPump01 controller (device_type=i2d) found in this iAquaLink account"
            )

        if self.serial:
            self.device = next(
                (
                    device
                    for device in self.devices
                    if device.get("serial_number") == self.serial
                ),
                None,
            )
            if self.device is None:
                raise IAqualinkNoDeviceError(
                    f"Configured iQPump01 controller {self._mask_suffix(self.serial)} "
                    "was not found in this iAquaLink account"
                )
            return

        self.device = self.devices[0]
        self.serial = self.device.get("serial_number")

    async def refresh_data(self):
        _LOGGER.debug("[refresh_data] Refreshing pump data.")
        payload = {
            "user_id": str(self.user_id),
            "command": "/alldata/read"
        }
        response_data = await self._post_control(payload, "refresh_data")
        self.data = response_data.get("alldata", {})
        return self.data

    async def set_opmode(self, opmode: OpMode):
        async with self._command_lock:
            await self._send_command("/opmode/write", int(opmode))

    async def set_custom_speed(self, rpm, duration_seconds):
        """Run the pump at `rpm` for `duration_seconds`, then revert to schedule.

        Requires three sequential writes: the controller ignores custom RPM
        writes while running in scheduled mode (opmode=0), so switch to
        custom mode before writing the target. Don't collapse or reorder.
        Returns the RPM actually written (rounded to the controller's step).
        """
        rpm = int(round(rpm / RPM_STEP) * RPM_STEP)
        async with self._command_lock:
            await self._send_command("/opmode/write", int(OpMode.CUSTOM))
            await self._send_command("/customspeedrpm/write", rpm)
            await self._send_command("/customspeedtimer/write", duration_seconds)
        return rpm

    async def _send_command(self, command, value):
        payload = {
            "user_id": str(self.user_id),
            "command": command,
            "params": f"value={value}",
        }
        _LOGGER.debug("[_send_command] POST %s | value=%s", command, value)
        data = await self._post_control(payload, "_send_command")

        # iAquaLink sometimes silently ignores writes; the echoed value is the
        # only acknowledgement we get.
        command_key = command.strip("/").split("/")[0]
        returned_value = data.get(command_key, {}).get("value")
        if returned_value is not None and str(returned_value) != str(value):
            raise IAqualinkCommandError(
                f"iAquaLink returned {command_key}={returned_value} "
                f"after requested {command_key}={value}"
            )
        return data
