[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/CLARENNE-Q/iaqualink_iqpump01)
![version](https://img.shields.io/badge/version-2.0.0-blue)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-%23FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/clarenneq)

# iAquaLink iQPump01

Control your Jandy iQPump01 variable-speed pool pump directly from Home Assistant — no third-party libraries, using the native iAquaLink/Zodiac API.

## ✅ Features

- Switch mode between auto (scheduled program), custom, and off from a single select
- Set a custom target RPM (in the pump's native 25 RPM steps) for a duration you set from a number entity
- Select the target iQPump01 controller when multiple pumps are linked to iAquaLink
- Monitor current speed, power consumption, and motor temperature
- Expose running and priming status as binary sensors
- Expose target RPM, custom RPM, and custom speed timer sensors
- Robust setup with duplicate detection, auth retry handling, and clear no-device errors
- Configurable faster refresh after speed changes to track real RPM ramp-up
- Configurable auto-refresh pump data polling
- HACS compatible for easy installation

## 🛠 Installation via HACS (recommended)

1. In HACS > Integrations, click the 3-dot menu > Custom Repositories
2. Add this repository: `https://github.com/CLARENNE-Q/iaqualink_iqpump01`
3. Choose category: Integration
4. Install the integration and restart Home Assistant
5. Go to **Settings > Devices & Services > Add Integration**, search for `iAquaLink iQPump01`

## ⚙️ Configuration

During setup, you'll need to provide:
- Your iAquaLink email
- Your iAquaLink password

No further configuration is needed.

## 📈 Entities created

Entity IDs are derived from the pump's device name, e.g.
`select.iaqualink_iqpump01_pool_mode` for a pump named "Pool".

| Entity | Description |
|--------|-------------|
| Mode (select) | `auto`, `custom`, `off` (plus read-only `quick_clean`, `timed_run`, `timed_stop`, `service` while active) |
| RPM target (number) | Target RPM — bounded by the pump's `globalrpmmin`/`globalrpmmax`, 25 RPM steps |
| Custom speed duration (number) | How long a custom speed runs before returning to the schedule (minutes, up to 23h59) |
| Running (binary sensor) | Whether the motor is running |
| Priming (binary sensor) | Whether the pump is priming |
| Power (sensor) | Power consumption (W) |
| Speed (sensor) | Current speed (RPM) |
| Motor temperature (sensor) | Motor temperature |
| Target RPM (sensor) | Requested target RPM |
| Custom speed RPM (sensor) | Custom speed RPM |
| Custom speed time remaining (sensor) | Remaining custom speed timer (seconds, `-1` when inactive) |

Firmware version and serial number appear on the device page. Raw pump state
(redacted) is available via **Download diagnostics** on the integration.

## 🧰 Services

| Service | Description |
|---------|-------------|
| `iaqualink_iqpump01.set_custom_speed` | Set the pump to a custom `rpm` for a specific `duration` (up to 23h59). Target the iQPump01 device. |


## 📌 Current limitations

- Only `i2d` controllers (iQPump01) are supported; other iAquaLink equipment families are not supported yet.
- Requires a valid iAquaLink account with at least one registered iQPump01 controller.
- Multi-pump is supported through multiple integration entries (one per serial), but there is no global cross-pump orchestration view/feature yet.
- Polling is configurable:
  - **Normal**: 60s by default (adjustable from 15 to 300s in options),
  - **Fast refresh** after speed changes: 10s by default for 3 minutes (adjustable from 5 to 60s and 30 to 600s).
  These guardrails help reduce cloud API rate-limiting risk.

## 🐞 Debugging

If you have another pump model and it doesn’t work out of the box, I may be able to investigate further **if you share the full raw API payloads** returned by your device.

### 🔍 How to enable debug logs

1. Edit your `configuration.yaml` (or go to **Settings > System > Logs > Configure**)
2. Add the following to enable detailed logs:

```yaml
logger:
  default: warning
  logs:
    custom_components.iaqualink_iqpump01: debug
```

3. Restart Home Assistant

### 📤 How to extract debug logs

Run this command from your Home Assistant terminal or SSH:

```bash
cat /config/home-assistant.log | grep iaqualink_iqpump01
```

This will filter the relevant debug messages from the integration.

> ⚠️ **Important**: Debug logs are automatically redacted by the integration, but always review them before pasting them in an issue. Remove any remaining email, password, authentication token, serial number, Wi-Fi SSID, address, or phone number.


## 🚀 Planned Features

- Support for multiple pumps (`i2d` devices)
- Automatic discovery of other iAquaLink-compatible devices
- Local API fallback (if available)
- Pump scheduling and advanced automation templates
- UI card suggestions for Lovelace Dashboard


## ⚖️ Disclaimer

This project is not affiliated with or endorsed by Zodiac, Jandy, or iAquaLink.  
It is a community-driven effort to bridge iQPump01 devices with Home Assistant using public and reverse-engineered API behavior.  
Use at your own risk.


## 🙏 Thanks

Big thanks to the Home Assistant community and to all the explorers diving into Zodiac APIs 🌊

Special thanks to Zodiac / iAquaLink / Jandy for creating reliable, high-quality smart pool equipment.

This project is not only a technical exploration, but also a way to promote and showcase the value of your connected pool systems. Many Home Assistant users are eager to integrate their iQPump01 into their smart home ecosystem.

If you are part of the Zodiac team, feel free to reach out via a GitHub issue. I’d be happy to explore collaboration opportunities — including the possibility of a local API for better real-time control and offline access.
