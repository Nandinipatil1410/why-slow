"""Everything that differs between Windows and Ubuntu lives in this folder.

The rest of the app only talks to a Probe, so it never needs to know the OS.
"""

import sys
from typing import Protocol


class Probe(Protocol):
    def waiting_signals(self) -> dict:
        """OS-specific "waiting" numbers, keyed by Snapshot field name."""
        ...

    def temperature_c(self) -> float | None: ...


class NullProbe:
    """Used on any OS we don't support yet: usage numbers still work, waiting ones are empty."""

    def waiting_signals(self) -> dict:
        return {}

    def temperature_c(self) -> float | None:
        return None


def get_probe() -> Probe:
    if sys.platform.startswith("linux"):
        from .linux import LinuxProbe

        return LinuxProbe()
    if sys.platform == "win32":
        from .windows import WindowsProbe

        return WindowsProbe()
    return NullProbe()
