"""Fake but realistic data for the last 24 hours, so you can try the page
without waiting a day. It's written to a separate demo database.

It contains three slowdowns:
- about 5 h ago: Chrome slowly leaks memory until the laptop chokes
- about 12 h ago: Windows Defender scans the disk
- about 2 h ago: VS Code pins the CPU
"""

import random

from .config import Config
from .models import AppUsage, Snapshot
from .storage import Store

TOTAL_MB = 8192


def build(store: Store, now: float, config: Config) -> None:
    rng = random.Random(42)
    leak_at, scan_at, cpu_at = now - 5 * 3600, now - 12 * 3600, now - 2 * 3600
    snaps = []
    ts = now - 24 * 3600
    while ts < now:
        chrome = 1200 + rng.uniform(-80, 80)
        code_cpu, defender_disk, latency = rng.uniform(1, 6), 0.0, rng.uniform(2, 6)
        mem_pressure, cpu_pressure, io_pressure = 0.0, rng.uniform(0, 4), rng.uniform(0, 3)

        if leak_at - 600 <= ts < leak_at + 480:  # Chrome grows for 8 min, then stays big
            chrome = 1200 + min((ts - (leak_at - 600)) / 480, 1) * 1900
            if ts >= leak_at - 120:
                mem_pressure = rng.uniform(25, 45)
        if scan_at <= ts < scan_at + 360:  # Defender reads the disk hard for 6 min
            defender_disk, latency, io_pressure = rng.uniform(60, 90), rng.uniform(40, 80), rng.uniform(30, 60)
        if cpu_at <= ts < cpu_at + 240:  # VS Code extension stuck in a loop
            code_cpu, cpu_pressure = rng.uniform(85, 95), rng.uniform(40, 70)

        used = 3500 + chrome
        snaps.append(
            Snapshot(
                ts=ts,
                cpu_percent=min(15 + code_cpu + rng.uniform(-5, 5), 100),
                ram_percent=used / TOTAL_MB * 100,
                ram_available_mb=TOTAL_MB - used,
                swap_percent=10,
                disk_read_mb_s=1 + defender_disk,
                disk_write_mb_s=0.5,
                disk_used_percent=71,
                cpu_freq_mhz=2400 + rng.uniform(-100, 100),
                heartbeat_lag_ms=rng.uniform(1, 8) + (cpu_pressure * 15 if cpu_pressure > 30 else 0),
                disk_latency_ms=latency,
                cpu_pressure=cpu_pressure,
                mem_pressure=mem_pressure,
                io_pressure=io_pressure,
                apps=[
                    AppUsage("chrome", rng.uniform(5, 15), chrome, 0.2),
                    AppUsage("code", code_cpu, 600, 0.1),
                    AppUsage("MsMpEng.exe", 2 + defender_disk / 10, 250, defender_disk),
                ],
            )
        )
        ts += config.snapshot_interval_s
    store.save(snaps)
    store.summarize_and_prune(now, config)
