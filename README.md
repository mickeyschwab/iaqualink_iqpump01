[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/mickeyschwab/iaqualink_iqpump01)
![version](https://img.shields.io/badge/version-2.0.0-blue)
[![CI](https://github.com/mickeyschwab/iaqualink_iqpump01/actions/workflows/ci.yml/badge.svg)](https://github.com/mickeyschwab/iaqualink_iqpump01/actions/workflows/ci.yml)

# iAquaLink iQPump01

Control a Jandy/Zodiac iQPump01 variable-speed pool pump from Home Assistant
through the native iAquaLink cloud API, with no third-party pool libraries.

> **This is a fork of
> [CLARENNE-Q/iaqualink_iqpump01](https://github.com/CLARENNE-Q/iaqualink_iqpump01)
> by [@CLARENNE-Q](https://github.com/CLARENNE-Q).** The original integration,
> including the reverse-engineered iAquaLink API client and the device
> behavior documented in [`docs/FIELD_NOTES.md`](docs/FIELD_NOTES.md), is
> their work. This fork redesigns how the pump is modeled in Home Assistant
> (see [What's different in this fork](#whats-different-in-this-fork)). See
> [Credits](#credits).

## Features

- **Mode** control: auto (the pump's schedule), custom, or off, from a single
  select.
- **Custom speed in RPM**: the pump's real range in 25 RPM steps, exactly as
  the iAquaLink app shows it.
- **`set_custom_speed` action** to run a given RPM for a given duration in
  one call, for automations and scripts.
- Sensors for speed, power, motor temperature, target and custom RPM, and
  time remaining on a custom speed.
- Running and priming binary sensors.
- Faster polling for a few minutes after a change, so you can watch the motor
  ramp up.
- Multiple pumps on one iAquaLink account, one integration entry per pump.
- Automatic re-authentication prompt when iAquaLink rejects your credentials.
- Redacted diagnostics download for troubleshooting.

## What's different in this fork

Version 2.0.0 of this fork reworks the upstream 1.x integration:

- **Speed is always in RPM.** The upstream 0–100 % control could drift when a
  value was read and written back (1975 RPM → 39 % → 1950 RPM).
- **One mode select** replaces the on/off switch, the return-to-program button,
  and the operating mode sensor. The old switch's "on" meant "return to
  schedule", which didn't match its state (whether the motor was running).
- **Re-authentication works.** Upstream had no reauth step, so an expired or
  changed password left the integration broken until it was re-added.
- **Wi-Fi SSID and serial number no longer land in the recorder database** as
  entity attributes; they're available through redacted diagnostics instead.
- Async HTTP client, typed pump state, a test suite, and CI.

**These are breaking changes.** [CHANGELOG.md](CHANGELOG.md) has the full list,
a table mapping old entities to new ones, and upgrade steps.

## Requirements

- Home Assistant 2024.11 or newer
- An iAquaLink account with at least one iQPump01 controller (`i2d` device)

## Installation (HACS)

1. In HACS, open the ⋮ menu → **Custom repositories**.
2. Add `https://github.com/mickeyschwab/iaqualink_iqpump01` with type
   **Integration**.
3. Download **iAquaLink iQPump01** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search for
   **iAquaLink iQPump01**.

If you're switching from the upstream repository, remove it in HACS first
(this keeps your configured integration), **back up Home Assistant**, then
follow the upgrade steps in [CHANGELOG.md](CHANGELOG.md#upgrading-from-1x).
Upgrading from 1.x can't be undone except by restoring that backup.

## Configuration

Setup asks for your iAquaLink email and password. If the account has more
than one iQPump01, you'll pick which one to add; add the integration again for
each additional pump.

**Options** (Settings → Devices & services → iAquaLink iQPump01 → Configure):

| Option | Default | Description |
|--------|---------|-------------|
| Default custom speed duration | 6 h (360 min) | How long a custom speed runs when set from the RPM target or by selecting `custom`, before the pump returns to its schedule. 1 min to 23 h 59. |
| Normal polling interval | 60 s | How often pump state is read (15–300 s). |
| Fast polling interval | 10 s | Polling interval right after a speed or mode change (5–60 s). |
| Fast polling duration | 180 s | How long fast polling lasts after a change (30–600 s). |

Polling is cloud-based; the guardrails on these values help avoid iAquaLink
rate limiting.

## Entities

Entity IDs are derived from the pump's device name, e.g.
`select.iaqualink_iqpump01_pool_mode` for a pump named "Pool".

| Entity | Description |
|--------|-------------|
| Mode (select) | `auto`, `custom`, `off`. While the pump is in quick clean, timed run, timed stop, or service mode, that mode is shown too, but it can't be selected remotely. |
| RPM target (number) | Sets a custom speed in RPM for the default duration. Bounded by the pump's own minimum and maximum. |
| Running (binary sensor) | Whether the motor is running. |
| Priming (binary sensor) | Whether the pump is priming, with priming timer, period, and RPM as attributes. |
| Speed (sensor) | Actual motor speed (RPM). Lags behind the target while ramping. |
| Power (sensor) | Power draw (W). |
| Motor temperature (sensor) | Motor temperature as reported by the pump. |
| Target RPM (sensor) | The speed the pump is currently aiming for. |
| Custom speed RPM (sensor) | The saved custom speed. |
| Custom speed time remaining (sensor) | Seconds left on the current custom speed; `-1` when none is running. |

Firmware version and serial number are shown on the device page.

## Controlling the pump

**From a dashboard**, add the Mode select and the RPM target. Setting an RPM
runs that speed for the default duration from the options, then the pump
returns to its schedule. Selecting `custom` resumes the saved custom speed for
the same default duration.

**From automations and scripts**, use the `set_custom_speed` action, which
takes the duration explicitly:

```yaml
action: iaqualink_iqpump01.set_custom_speed
data:
  device_id: <your pump's device ID>
  rpm: 2800
  duration: "02:00:00"
```

`rpm` must be within the pump's range; out-of-range values are rejected rather
than clamped. `duration` can be up to 23 h 59. To return to the schedule early,
set the Mode select to `auto`.

If the pump is in service mode (remote control locked at the pump), every
control raises an error instead of silently doing nothing.

## Limitations

- Only iQPump01 controllers (`device_type` `i2d`) are supported. Other
  iAquaLink equipment isn't.
- Cloud polling only; iAquaLink offers no local API.
- Quick clean, timed run, and timed stop can be displayed but not started
  remotely: writing those modes hasn't been confirmed to work.

## Troubleshooting

**Diagnostics:** on the integration's page, open the ⋮ menu → **Download
diagnostics**. The file contains the pump's current state with emails, tokens,
serial numbers, Wi-Fi SSID, and address fields redacted.

**Debug logs:** add this to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.iaqualink_iqpump01: debug
```

Then filter the log:

```bash
grep iaqualink_iqpump01 /config/home-assistant.log
```

Logged API responses are redacted automatically, but review logs before
posting them in an issue.

If you have a different Jandy pump model, diagnostics and debug logs from it
are the most useful thing to include in an
[issue](https://github.com/mickeyschwab/iaqualink_iqpump01/issues).

## Development

```bash
pip install -r requirements_test.txt
pytest
```

The tests run the integration inside a real Home Assistant instance against a
simulated pump; nothing talks to the iAquaLink cloud. CI also runs `hassfest`
and HACS validation. See [`CLAUDE.md`](CLAUDE.md) for an architecture overview
and [`docs/FIELD_NOTES.md`](docs/FIELD_NOTES.md) for observed device behavior.

## Credits

This integration was created by [@CLARENNE-Q](https://github.com/CLARENNE-Q)
as [iaqualink_iqpump01](https://github.com/CLARENNE-Q/iaqualink_iqpump01).
The iAquaLink login and control API client, the discovery of the pump's
operating modes, the custom-speed write sequence, and the field notes this fork
relies on all come from that project. If this integration is useful to you,
consider supporting the original author:

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-%23FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/clarenneq)

Thanks also to the Home Assistant community and everyone who has explored the
Zodiac/iAquaLink APIs.

## Disclaimer

This project is not affiliated with or endorsed by Zodiac, Jandy, or
iAquaLink. It uses reverse-engineered API behavior and may stop working if
iAquaLink changes its API. Use at your own risk.
