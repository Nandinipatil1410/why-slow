"""The shape of the data we record.

A Snapshot is one moment of the whole laptop. It holds two kinds of numbers:
- usage: how busy things are (CPU %, RAM %), which is what Task Manager shows
- waiting: how long programs were stuck, which is what you actually feel as "slow"

Waiting signals differ by OS, so each one is optional (None = not available here).
"""

from dataclasses import dataclass, field


@dataclass
class AppUsage:
    """One app at one moment. All processes with the same name are added together,
    so Chrome's 30 processes count as one "chrome" entry."""

    name: str
    cpu_percent: float  # share of the whole machine, 0-100
    ram_mb: float
    # Reads + writes, MB/s. On Windows this also counts reads served from memory
    # cache, so it can be far above what the disk really did. Treat it as
    # "I/O activity", and trust it only when the laptop's disk is busy too.
    io_mb_s: float


@dataclass
class Snapshot:
    ts: float  # unix time, seconds

    # Usage
    cpu_percent: float
    ram_percent: float
    ram_available_mb: float
    swap_percent: float
    disk_read_mb_s: float
    disk_write_mb_s: float
    disk_used_percent: float  # how full the system drive is
    cpu_freq_mhz: float | None = None  # drops when the laptop overheats or saves power
    temp_c: float | None = None  # Ubuntu only in v1

    # Waiting, on both OSes
    heartbeat_lag_ms: float | None = None  # how late the collector itself woke up
    disk_latency_ms: float | None = None  # average time per disk read/write

    # Waiting, Ubuntu only: % of time some program was stuck (kernel "PSI", avg over 10 s)
    cpu_pressure: float | None = None
    mem_pressure: float | None = None
    io_pressure: float | None = None

    # Waiting, Windows only
    hard_faults_per_s: float | None = None  # memory pages fetched back from disk
    foreground_app: str | None = None  # the app whose window you're using
    foreground_hung: bool | None = None  # True if Windows marks it "Not Responding"

    apps: list[AppUsage] = field(default_factory=list)
