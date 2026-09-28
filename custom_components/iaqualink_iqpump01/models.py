"""Device-level types for the iQPump01, independent of Home Assistant."""

from dataclasses import dataclass
from enum import IntEnum


class OpMode(IntEnum):
    """iQPump01 `opmode` values (see docs/FIELD_NOTES.md)."""

    AUTO = 0
    CUSTOM = 1
    OFF = 2
    QUICK_CLEAN = 3
    TIMED_RUN = 4
    TIMED_STOP = 5
    # iAquaLink reports "remote control not authorized"; the pump UI shows off.
    SERVICE = 7


# Modes with confirmed remote writes (see docs/FIELD_NOTES.md).
WRITABLE_OPMODES = (OpMode.AUTO, OpMode.CUSTOM, OpMode.OFF)

# Fallbacks when the pump doesn't report globalrpmmin/globalrpmmax.
DEFAULT_RPM_MIN = 1000
DEFAULT_RPM_MAX = 3450


def _number(value):
    """Coerce an iAquaLink string field to int (or float), or None."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class PumpState:
    """Typed view of an `/alldata/read` response.

    iAquaLink reports every field as a string; this is the one place that
    parses them. `raw` keeps the original payload for diagnostics.
    """

    raw: dict
    opmode: OpMode | None
    running: bool | None
    rpm_target: int | None
    custom_speed_rpm: int | None
    # Remaining seconds; -1 means inactive.
    custom_speed_timer: int | None
    rpm_min: int
    rpm_max: int
    motor_speed: int | float | None
    motor_power: int | float | None
    motor_temperature: int | float | None
    # Remaining seconds; -1 means not priming.
    priming_timer: int | None
    priming_period: int | None
    priming_rpm: int | None

    @classmethod
    def from_alldata(cls, data: dict) -> "PumpState":
        motor = data.get("motordata") or {}
        try:
            opmode = OpMode(int(data.get("opmode")))
        except (TypeError, ValueError):
            opmode = None
        runstate = data.get("runstate")
        return cls(
            raw=data,
            opmode=opmode,
            running=None if runstate is None else runstate == "on",
            rpm_target=_number(data.get("rpmtarget")),
            custom_speed_rpm=_number(data.get("customspeedrpm")),
            custom_speed_timer=_number(data.get("customspeedtimer")),
            rpm_min=_number(data.get("globalrpmmin")) or DEFAULT_RPM_MIN,
            rpm_max=_number(data.get("globalrpmmax")) or DEFAULT_RPM_MAX,
            motor_speed=_number(motor.get("speed")),
            motor_power=_number(motor.get("power")),
            motor_temperature=_number(motor.get("temperature")),
            priming_timer=_number(data.get("primingtimer")),
            priming_period=_number(data.get("primingperiod")),
            priming_rpm=_number(data.get("primingrpm")),
        )

    @property
    def is_priming(self) -> bool | None:
        if self.priming_timer is None:
            return None
        return self.priming_timer >= 0
