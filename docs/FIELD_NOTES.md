# iAquaLink iQPump01 Field Notes

This document captures practical findings learned while debugging and improving the
`iaqualink_iqpump01` Home Assistant custom integration. It is intentionally focused
on observed behavior and implementation decisions, not on private user data.

## Scope

- The integration currently targets Jandy/Zodiac iQPump01 controllers exposed by
  iAquaLink as `device_type=i2d`.
- Other Jandy variable-speed pumps may use different `device_type` values and are
  not confirmed supported.
- Pool heater support is not implemented. Heater support would require separate
  API discovery and separate entities.

## Authentication And Device Discovery

Known flow:

1. `POST https://prod.zodiac-io.com/users/v1/login`
2. Extract auth/session data from the login response.
3. `GET https://r-api.iaqualink.net/devices.json`
4. Select devices where `device_type == "i2d"` and `serial_number` exists.

Implementation notes:

- Debug logs must redact sensitive fields such as email, address, tokens, session
  IDs, AWS credentials, phone numbers, Wi-Fi SSID, and serial numbers.
- The integration now raises explicit errors for authentication failure, network
  failure, and no iQPump01 device found.
- Multiple iQPump01 controllers can exist in one iAquaLink account. The config
  flow should let the user select which `serial_number` to configure.
- Existing legacy entries without a stored `serial` can still load by using the
  first detected iQPump01, then saving the detected serial back to the entry.

## Control Endpoint

Known control endpoint:

```text
POST https://r-api.iaqualink.net/v2/devices/{serial}/control.json?
```

Common payload shape:

```json
{
  "user_id": "<user_id>",
  "command": "/alldata/read"
}
```

Command payload shape:

```json
{
  "user_id": "<user_id>",
  "command": "/customspeedrpm/write",
  "params": "value=2225"
}
```

The integration uses iAquaLink-style headers including session cookie,
authorization token, API key, and a mobile app user-agent.

## Known Commands

Observed useful commands:

| Purpose | Command | Params |
| --- | --- | --- |
| Read all state | `/alldata/read` | none |
| Return to auto mode | `/opmode/write` | `value=0` |
| Enter custom/manual speed mode | `/opmode/write` | `value=1` |
| Turn off | `/opmode/write` | `value=2` |
| Set custom RPM | `/customspeedrpm/write` | `value=<rpm>` |
| Set custom speed timer | `/customspeedtimer/write` | `value=<seconds>` |

Important behavior:

- Writing `customspeedrpm` while the pump is in scheduled mode may be ignored.
- The reliable custom-speed sequence is:
  1. Write `/opmode/write` with `value=1`.
  2. Write `/customspeedrpm/write` with the desired RPM.
  3. Write `/customspeedtimer/write` with the desired duration.
- Returning to the normal schedule/Auto mode is done by writing `/opmode/write`
  with `value=0`.
- Service mode (`opmode=7`) is not remotely controllable. Home Assistant should
  block write commands instead of trying to force pump control while the
  iAquaLink app reports remote control is not authorized. The mode select
  shows this as `service` (the iQPump01 interface itself shows `off`).
- If iAquaLink returns a different value than requested, Home Assistant should
  show a visible command error instead of silently accepting the state.

## Operating Modes

Observed `opmode` values:

| `opmode` | Meaning |
| --- | --- |
| `0` | Auto mode |
| `1` | Custom/manual speed mode |
| `2` | Off |
| `3` | Quick Clean |
| `4` | Timed Run |
| `5` | Timed Stop |
| `7` | Off/service mode; remote control not authorized |

Home Assistant exposes this as a single **Mode** select with options `auto`,
`custom`, `off`, `quick_clean`, `timed_run`, `timed_stop`, and `service`. Only
`auto` (0), `custom` (1), and `off` (2) have confirmed remote writes, so those
are always offered; the others appear only while the pump is in them and are
rejected if selected. Selecting `custom` resumes the saved `customspeedrpm`
using the full three-write custom-speed sequence.

Whether the motor is actually spinning is `runstate` (`on`/`off`), exposed as
a separate running binary sensor — `auto` mode can legitimately be not
running if the schedule says so.

Related fields:

- `runstate`: usually `on` or `off`.
- `rpmtarget`: current target RPM reported by the controller.
- `customspeedrpm`: custom/manual target RPM.
- `customspeedtimer`: remaining custom/manual timer seconds, or `-1` when inactive.
- `motordata.speed`: actual motor speed, which can lag behind target changes.

## RPM Control

The Home Assistant number entity is expressed directly in RPM, matching what the
iAquaLink app displays — there is no percentage mapping:

- Minimum from `globalrpmmin`, fallback `1000`.
- Maximum from `globalrpmmax`, fallback `3450`.
- Step is 25 RPM; requested RPM is also rounded to the nearest 25 RPM before
  writing, since the controller only accepts targets in 25 RPM increments.
- The displayed value is the controller-reported `rpmtarget`.

Earlier versions exposed a `0–100%` number. That mapping truncated in both
directions, so reading a value and setting it back could drift the RPM (e.g.
`1975` RPM displayed as `39%`, which wrote back as `1950`). It was removed.

## Timers

Observed timer convention:

- `-1` generally means inactive.
- `0` or positive values generally mean active or counting down.

Custom speed timer:

- `customspeedtimer=-1`: no active custom speed timer.
- `customspeedtimer>=0`: active custom speed timer.

The integration's custom speed duration is a Home Assistant number entity in
minutes (`1`–`1439`, default 6 h), restored across restarts. The iAquaLink
mobile app appears to allow up to approximately `23 h 59`, so that's the cap.

## Priming

Priming can be detected from `primingtimer`.

Observed rule:

```python
is_priming = int(data.get("primingtimer", -1)) >= 0
```

Related fields:

- `primingtimer`: remaining priming seconds, or `-1` when not priming.
- `primingperiod`: configured priming duration.
- `primingrpm`: configured priming RPM.
- `motordata.speed`: actual current RPM, which can be higher than `rpmtarget`
  during priming.

Example interpretation:

```json
{
  "opmode": "0",
  "runstate": "on",
  "rpmtarget": "1500",
  "primingperiod": "60",
  "primingrpm": "2000",
  "primingtimer": "40",
  "motordata": {
    "speed": "2874"
  }
}
```

This means the pump is likely in priming because `primingtimer=40`.

The integration exposes this as a binary sensor:

a priming binary sensor with `priming_timer`, `priming_period`, and
`priming_rpm` attributes.

## Polling And Refresh Behavior

Observed behavior:

- The iAquaLink app and API can take many seconds before actual motor speed
  catches up after a target RPM change.
- `rpmtarget` may update quickly, while `motordata.speed` ramps up more slowly.
- A normal polling interval around `60s` can make RPM changes appear delayed.

Implementation decision:

- Use Home Assistant `DataUpdateCoordinator`.
- Normal polling interval is configurable.
- Fast polling is enabled after RPM changes to track motor speed ramp-up.
- Fast polling interval and fast polling duration are configurable.

Default values:

- Normal polling: `60s`
- Fast polling: `10s`
- Fast polling duration after RPM change: `180s`

## Home Assistant Entities

Entities use Home Assistant's `has_entity_name` naming, so entity IDs are
derived from the device name (e.g. `select.iaqualink_iqpump01_pool_mode` for a
pump named "Pool"). Entities:

- Mode select (replaces the former on/off switch, return-to-program button,
  and operating mode sensor)
- RPM target number
- Custom speed duration number (config)
- Running binary sensor from `runstate`
- Priming binary sensor
- Pump speed sensor from `motordata.speed`
- Pump power sensor from `motordata.power`
- Pump motor temperature sensor from `motordata.temperature`
- Target RPM sensor from `rpmtarget`
- Custom RPM sensor from `customspeedrpm`
- Custom speed timer sensor from `customspeedtimer`

The exact entity IDs can vary depending on Home Assistant's entity registry and
user customizations.

Raw pump state (redacted) is available from the integration's **Download
diagnostics** instead of entity attributes, so SSIDs, serials, and similar
values never land in the recorder database.

## Services

`iaqualink_iqpump01.set_custom_speed` is a domain-level service (registered in
`__init__.py`'s `async_setup`, not tied to any single entity platform) that
sets a custom RPM target for a specific duration in one call, matching the
"set X rpm for X time" control in the iAquaLink app. The RPM number
entity and selecting `custom` mode use the custom speed duration entity; this
service takes its own duration instead, so one call can set both.

- Fields: `rpm` (raw RPM, matching what the iAquaLink app displays) and
  `duration` (HA duration selector, day component disabled).
- Target is the iQPump01 **device** (`device_id` field, multiple allowed; its
  device selector is restricted to `integration: iaqualink_iqpump01`. It's a
  field rather than a service `target` because HA rejects device filters on
  targets; `target: device_id:` in YAML still works). `IAqualinkPumpCoordinator.async_get_by_device_id(hass, device_id)`
  resolves a device_id to its coordinator (the device's loaded config
  entries' `runtime_data`) — this is a general-purpose resolver
  on the coordinator class, not something private to this service, so any
  future device-targeted service can reuse it. The handler in `__init__.py`
  resolves every targeted device first (raising if any is unrecognized), then
  runs `coordinator.async_set_custom_speed_rpm(rpm, duration_seconds)`
  concurrently across all of them via `asyncio.gather` — each targeted pump
  is an independent physical device with its own HTTP session, so there's no
  reason to serialize across pumps (the three-write ordering constraint only
  applies within a single pump's own sequence).
- `rpm` is validated against the pump's live `globalrpmmin`/`globalrpmmax`;
  out-of-range values raise a clear error rather than being silently clamped.
- `duration` is validated against `MAX_CUSTOM_SPEED_TIMER_SECONDS` (23h59, the
  same ceiling the app enforces) before any write happens.
- The actual write sequence (and the service-mode guard) live in
  `IAqualinkPumpCoordinator._async_write_custom_speed(rpm, duration_seconds)`,
  which rounds to the nearest 25 RPM the controller accepts. Both the
  number entity and the service call `async_set_custom_speed_rpm(rpm, ...)`,
  which validates the range and funnels into it — extend that helper, don't
  duplicate the three-write sequence.

## Config Flow And Options Flow

Config flow behavior:

- Login with iAquaLink credentials.
- Discover iQPump01 controllers.
- If one controller is found, configure it directly.
- If multiple controllers are found, show a selection step.
- Use the selected serial as the config entry `unique_id`.
- Abort duplicates using Home Assistant's unique ID handling.

Options flow exposes:

- Normal polling interval.
- Fast polling interval after RPM change.
- Fast polling duration after RPM change.

Changing options reloads the integration so the coordinator uses the new values.

## Network And Error Handling

Implementation decisions:

- All HTTP calls use a 15s `aiohttp.ClientTimeout`.
- HTTP error statuses are checked (`_raise_for_status`) before parsing.
- `401` and `403` should map to authentication errors.
- Connection/timeouts should map to retryable setup/update errors.
- Login failures should become `ConfigEntryAuthFailed`.
- Temporary network/API failures during setup should become `ConfigEntryNotReady`.
- No iQPump01 found should be visible during config flow and retryable during
  setup.

## Known Limitations

- Only `device_type=i2d` is currently supported.
- Raw iAquaLink API behavior is reverse-engineered and may change.
- Direct selection/enabling of named iAquaLink schedules is not implemented.
- Pool heater support is not implemented.
- The integration does not yet include automated tests or CI.
- Command retry/backoff for ignored RPM writes could be improved further.

## Useful Debug Checklist

When a user reports pump speed or mode issues, ask for redacted debug logs around:

- The `async_set_value` call.
- `/opmode/write`
- `/customspeedrpm/write`
- `/customspeedtimer/write`
- The immediate `/alldata/read` refresh.
- A later refresh 30-90 seconds after the command.

Key fields to compare:

- `opmode`
- `runstate`
- `rpmtarget`
- `customspeedrpm`
- `customspeedtimer`
- `primingtimer`
- `motordata.speed`
- `globalrpmmin`
- `globalrpmmax`

Avoid asking users to share raw login responses or unredacted payloads because
they can contain tokens, addresses, phone numbers, and other private data.
