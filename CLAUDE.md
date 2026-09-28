# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (HACS component) that controls Jandy/Zodiac
iQPump01 variable-speed pool pumps through the native iAquaLink/Zodiac cloud API
(`cloud_polling`, no local API, no third-party pool libraries). The integration
domain is `iaqualink_iqpump01`; all code lives under
`custom_components/iaqualink_iqpump01/`.

There is currently no test suite, no lint config, and no CI workflow in this repo
— `docs/AUDIT_RECOMMENDATIONS.md` calls this out explicitly as a gap. Don't assume
tooling that isn't present; verify changes by reading the code path and, where
possible, checking Python syntax (see Commands below).

## Commands

There is no build step (Home Assistant loads the component directly) and no
configured test/lint tooling. Useful ad hoc checks:

```bash
# Syntax-check all component files
python3 -m py_compile custom_components/iaqualink_iqpump01/*.py

# Validate JSON (manifest, hacs.json, translations)
python3 -m json.tool hacs.json > /dev/null
python3 -m json.tool custom_components/iaqualink_iqpump01/manifest.json > /dev/null
```

Bump the version in **both** `hacs.json` and
`custom_components/iaqualink_iqpump01/manifest.json` together when releasing —
they're expected to stay in sync (currently `1.0.18`).

## Architecture

### Data flow

1. **`api.py` — `IAqualinkClient`**: thin synchronous `requests`-based client
   (not `aiohttp`; calls are pushed to the executor via
   `hass.async_add_executor_job`). Handles:
   - `login()` — POSTs to `prod.zodiac-io.com/users/v1/login`, then lists
     devices from `r-api.iaqualink.net/devices.json` and filters to
     `device_type == "i2d"` (the only supported controller family).
   - `refresh_data()` — POSTs `/alldata/read` to the per-serial control
     endpoint and stores the full state blob in `self.data`.
   - `_send_command(command, param)` — POSTs a write command (e.g.
     `/opmode/write` with `value=1`) and cross-checks the echoed value against
     what was requested, raising `IAqualinkCommandError` on mismatch (iAquaLink
     sometimes silently ignores writes — see Field Notes below).
   - All responses are redacted before logging (`_redact_for_log`) — emails,
     tokens, SSIDs, serials, etc. Preserve this when touching logging code;
     never log raw payloads.
   - Typed exceptions (`IAqualinkAuthError`, `IAqualinkConnectionError`,
     `IAqualinkNoDeviceError`, `IAqualinkCommandError`) are the contract the
     rest of the integration relies on to map failures to the right Home
     Assistant behavior.

2. **`coordinator.py` — `IAqualinkPumpCoordinator`** (`DataUpdateCoordinator`):
   owns polling cadence and translates client exceptions to HA's expected
   types (`ConfigEntryAuthFailed`, `UpdateFailed`). Supports a **fast-refresh
   mode**: after a speed-changing command, `enable_fast_refresh()` temporarily
   shortens the poll interval (default 10s for 3 minutes) because
   `motordata.speed` ramps up slowly after `rpmtarget` changes — normal 60s
   polling makes changes look stuck. Both intervals and the fast-refresh
   window are user-configurable via the options flow. It also owns all pump
   *control* logic — `raise_if_service_mode()`,
   `async_set_custom_speed_rpm(rpm, duration)` (range-validating entry point,
   used by both the number entity and the service), and
   `_async_write_custom_speed(rpm, duration)` for the actual three-write
   sequence — rather than the entities, since this logic is
   per-device, not per-entity; see point 4.

3. **`entity.py` — `IAqualinkPumpEntity`** (base `CoordinatorEntity`): shared
   device_info, and a thin `_raise_if_service_mode()` wrapper that delegates to
   the coordinator. Pump `opmode == "7"` means iAquaLink reports "remote
   control not authorized" (physical service mode). Every write-capable
   entity must call this guard before sending a command, raising
   `HomeAssistantError` instead of silently failing.

4. **Platforms** (`switch.py`, `number.py`, `sensor.py`, `button.py`,
   `binary_sensor.py`): each reads from `coordinator.data` (the raw
   `alldata` dict); writes go through the coordinator rather than calling
   `client._send_command` directly (see `number.py`'s `async_set_value`,
   which just calls `coordinator.async_set_custom_speed_rpm()`). Simple on/off
   writes (`switch.py`, `button.py`) still call `client._send_command`
   directly since they don't share logic with anything else. There is exactly
   one entity per platform today (single switch, single number, one button,
   one binary sensor) — `sensor.py` is the one platform with multiple
   entities, defined declaratively via the `FIELDS` dict (path into `alldata`,
   unit, device_class, state_class).

5. **`config_flow.py`**: login step → if the account has more than one `i2d`
   device, a `select_pump` step lets the user pick a `serial_number`, which
   becomes the config entry's `unique_id` (duplicate entries are blocked via
   `_abort_if_unique_id_configured`). The options flow tunes the four polling
   knobs in `const.py` (custom speed timer, normal interval, fast interval,
   fast duration) and triggers a reload on change.

6. **`__init__.py`**: sets up the client, coordinator, forwards to all
   `PLATFORMS`, and on unload calls `coordinator.async_shutdown()` to cancel
   the fast-refresh timer. `async_setup()` also registers the
   `iaqualink_iqpump01.set_custom_speed` domain-level service (`services.yaml`,
   target: `device_id`, field `rpm`), which lets one call set a raw RPM target
   *and* an arbitrary duration together — the number entity's plain
   `async_set_value` only ever uses the options-flow preset duration. The
   handler resolves each targeted `device_id` via
   `IAqualinkPumpCoordinator.async_get_by_device_id()` (a reusable
   classmethod, not one-off logic — the resolution belongs on the coordinator
   since any future device-targeted service needs the same lookup), then runs
   `coordinator.async_set_custom_speed_rpm()` concurrently across all targeted
   pumps via `asyncio.gather`. It's a domain-level service
   rather than an entity service on the `number` platform so it can be
   targeted at the pump device itself. Out-of-range values raise a
   `HomeAssistantError` rather than being silently clamped.

### Key domain knowledge (see `docs/FIELD_NOTES.md` for full detail)

- `opmode` values: `0` auto, `1` custom/manual, `2` off, `3` quick clean,
  `4` timed run, `5` timed stop, `7` service mode (displayed as `off`, but
  internally still blocks remote writes — see `OPMODE_SERVICE` in `const.py`).
- Setting a custom RPM requires **three sequential writes**: `opmode=1`, then
  `customspeedrpm`, then `customspeedtimer` — writing RPM directly while in
  scheduled mode is ignored by the controller. This sequence lives in
  `coordinator.py`'s `_async_write_custom_speed()`; don't collapse or reorder
  it.
- Speed is RPM everywhere — the integration deliberately never uses a
  percentage (an earlier 0–100% number drifted on round-trips). The number
  entity's min/max come from `globalrpmmin`/`globalrpmmax` in device state
  (fallback `1000`/`3450`, see `const.rpm_limits()`), step 25 RPM.
- Priming is inferred as `primingtimer >= 0` (a timer value of `-1` means
  inactive) — the same "`-1` = inactive" convention applies to
  `customspeedtimer`.
- `docs/AUDIT_RECOMMENDATIONS.md` records known technical debt (sync
  `requests` vs `aiohttp`, hardcoded headers, partial command-ack validation,
  broad `except Exception` in the coordinator) — check it before making
  related changes, since it documents deliberate tradeoffs as well as gaps.

### Translations

`custom_components/iaqualink_iqpump01/translations/*.json` must stay in sync
with `en.json`'s keys (config flow steps/errors, options flow fields) across
all locales (de, es, fr, it, nl) when adding or renaming a config/options
field.
