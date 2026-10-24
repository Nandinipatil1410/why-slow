"""Ubuntu: read the kernel's pressure numbers (PSI) and CPU temperature.

PSI answers "what % of the last 10 s was at least one program stuck waiting
for CPU / memory / disk?". It's the most direct "slowness" number any OS gives.
Needs Linux 4.20+, which every current Ubuntu has.
"""

from pathlib import Path

import psutil

PSI_DIR = Path("/proc/pressure")

# Sensor names used by common laptop chips, best first.
CPU_SENSORS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")


def parse_psi_some_avg10(text: str) -> float | None:
    """Pull the 'some avg10' value out of a /proc/pressure file.

    Example input:
        some avg10=12.50 avg60=3.10 avg300=0.80 total=123456
        full avg10=0.00 avg60=0.00 avg300=0.00 total=0
    """
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "some":
            for part in parts[1:]:
                key, _, value = part.partition("=")
                if key == "avg10":
                    return float(value)
    return None


class LinuxProbe:
    def waiting_signals(self) -> dict:
        signals = {}
        for resource, field_name in (("cpu", "cpu_pressure"), ("memory", "mem_pressure"), ("io", "io_pressure")):
            try:
                signals[field_name] = parse_psi_some_avg10((PSI_DIR / resource).read_text())
            except OSError:
                signals[field_name] = None  # older kernel, or PSI turned off
        return signals

    def temperature_c(self) -> float | None:
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, OSError):
            return None
        for name in CPU_SENSORS:
            readings = [r.current for r in sensors.get(name, []) if r.current]
            if readings:
                return max(readings)
        return None
