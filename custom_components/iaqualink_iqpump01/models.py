"""Device-level types for the iQPump01, independent of Home Assistant."""

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
