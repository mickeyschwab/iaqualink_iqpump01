# Changelog

## 2.0.1

- The **RPM target** number is now **Custom speed** and shows the saved
  custom speed (`customspeedrpm`) instead of `rpmtarget`, which in `auto`
  follows the schedule. Its entity ID is unchanged.
- Removed the **Target RPM** and **Custom speed RPM** sensors; they duplicated
  the number. The **Speed** sensor is renamed **Actual speed**. The old sensors
  aren't removed from the registry automatically, so delete them by hand.
- **Motor temperature** is now a temperature sensor in °C, so Home Assistant
  converts it to your unit system. **Custom speed time remaining** is now a
  duration sensor.

## 2.0.0

A redesign of how the pump is modeled in Home Assistant: speed is always in
RPM, operating mode is a single select, and the integration now uses current
Home Assistant conventions. **This release contains breaking changes**, so read
[Upgrading from 1.x](#upgrading-from-1x) before installing.

Requires **Home Assistant 2024.11 or newer**.

### Breaking changes

Several entities were replaced. On upgrade, the integration removes the old
ones from the entity registry automatically, so they won't linger as
"unavailable". Automations, scripts, and dashboards that use them need to be
updated by hand.

| Removed (1.x) | Replacement (2.0.0) |
| --- | --- |
| `switch.pump_i2d` | **Mode** select: `auto` replaces "on", `off` replaces "off". Whether the motor is actually spinning is the new **Running** binary sensor. |
| `button.pump_return_to_program` | **Mode** select → `auto` |
| `number.pump_rpm_target_percentage` (0–100 %) | **RPM target** number, in RPM (the pump's own min/max, 25 RPM steps) |
| `sensor.pump_operating_mode` | The **Mode** select's state |
| Attributes on `switch.pump_i2d` | **Motor temperature** sensor; firmware version and serial on the device page; priming details on the **Priming** sensor; everything else via **Download diagnostics** |

Other breaking changes:

- **Mode values changed.** The mode select's states are `auto`, `custom`,
  `off`, `quick_clean`, `timed_run`, `timed_stop`, and `service`. The old
  operating mode sensor used `quick clean` / `timed run` / `timed stop` (with
  spaces) and showed service mode as `off`.
- **New entity IDs.** New entities are named from the device, e.g.
  `select.iaqualink_iqpump01_pool_mode` for a pump named "Pool". Sensors that
  already existed (speed, power, target RPM, custom speed RPM, custom speed
  timer) keep their current entity IDs.
- **No downgrade path.** Upgrading migrates the config entry to a new version
  that 1.x can't load. To roll back, restore a Home Assistant backup taken
  before upgrading.

### New

- **Mode select.** `auto` (scheduled program), `custom`, and `off` can always
  be selected. Quick clean, timed run, timed stop, and service mode are shown
  while the pump is in them, but can't be selected: remote writes for them
  aren't confirmed. Selecting `custom` resumes the pump's saved custom speed
  for the configured duration.
- **RPM target number** with the pump's real range (`globalrpmmin` to
  `globalrpmmax`) and 25 RPM steps. It shows exactly what the iAquaLink app
  shows.
- **Any custom speed duration.** The options setting is now a minutes box
  (up to 23 h 59, matching the iAquaLink app) instead of five presets. It's
  the default for the RPM target and for selecting `custom`; your existing
  setting carries over. For a one-off duration, use the `set_custom_speed`
  action.
- **Running** binary sensor (from `runstate`) and **Motor temperature**
  sensor.
- **Diagnostics download** with redacted pump state, for troubleshooting.
- Firmware version and serial number on the device page.
- Entity names and mode labels are translated (French included; other
  locales currently fall back to English text).

The `iaqualink_iqpump01.set_custom_speed` service works as before. In the UI
the pump is now picked with a **Pump** field instead of a target, because
current Home Assistant rejects the old definition. Existing YAML using
`target: device_id: ...` keeps working.

### Fixes

- **Re-authentication now works.** When iAquaLink rejected the saved
  credentials (password changed, session revoked), Home Assistant's
  "re-authenticate" prompt failed, and the integration stayed broken until it
  was deleted and re-added. It now asks for the current password and reloads.
- **Speed no longer drifts.** The percentage control rounded down in both
  directions, so reading a value and setting it back could change the speed
  (1975 RPM showed as 39 %, which wrote back as 1950 RPM).
- **The on/off switch could contradict itself.** "On" meant "return to
  schedule", but the switch showed whether the motor was running. Turning it
  on while the schedule had the pump off left it showing off. The Mode select
  and Running sensor now report these separately.
- **Less sensitive data stored.** Wi-Fi SSID, serial number, and other raw
  fields were exposed as switch attributes, and therefore written to the
  recorder database. They're now only available via redacted diagnostics.
  Redaction also now masks the serial number stored in the config entry.

### Under the hood

- Async `aiohttp` client using Home Assistant's shared session, replacing
  blocking `requests` calls.
- Typed pump state, parsed once per poll instead of in every entity.
- The three-step custom-speed write sequence is serialized per pump, so two
  commands can't interleave.
- Test suite (`pytest-homeassistant-custom-component`) and CI running tests,
  `hassfest`, and HACS validation.
- Metadata (documentation, issue tracker, code owner) points to this fork.

### Upgrading from 1.x

1. **Back up Home Assistant** (Settings → System → Backups). There's no
   downgrade path other than restoring a backup.
2. *Optional:* enable debug logging so the upgrade is visible in the log:
   ```yaml
   logger:
     logs:
       custom_components.iaqualink_iqpump01: debug
   ```
3. Update through HACS and restart Home Assistant. The log shows
   `Removing entity ... (removed in 2.0.0)` for each replaced entity.
4. Update automations, scripts, and dashboards using the table above. For
   example:

   ```yaml
   # 1.x
   - action: switch.turn_on
     target:
       entity_id: switch.pump_i2d
   - action: number.set_value
     target:
       entity_id: number.pump_rpm_target_percentage
     data:
       value: 50

   # 2.0.0
   - action: select.select_option
     target:
       entity_id: select.iaqualink_iqpump01_pool_mode
     data:
       option: auto
   - action: number.set_value
     target:
       entity_id: number.iaqualink_iqpump01_pool_rpm_target
     data:
       value: 2225
   ```

   A 1.x percentage converts to RPM as
   `min + percent / 100 × (max − min)`, rounded to 25. With the default
   1000–3450 RPM range, 50 % is 2225 RPM. Your pump's actual range is shown
   on the RPM target entity.
5. Check that the integration's options show the default custom speed
   duration you expect.
