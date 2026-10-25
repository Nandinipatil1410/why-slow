"""Takes a snapshot every 5 s and hands batches of them to storage.

Two parts:
- Sampler: reads the numbers for one moment.
- Collector: the loop. It wakes every 5 s, measures how late it woke
  (the heartbeat), keeps snapshots in memory, and saves them once a minute.
"""

import os
import threading
import time
from dataclasses import dataclass

import psutil

from .config import Config
from .models import AppUsage, Snapshot
from .platforms import Probe

MB = 1024 * 1024


@dataclass
class ProcessSample:
    name: str
    cpu_percent: float  # psutil style: 100 = one full core
    ram_bytes: int
    io_bytes_per_s: float


def group_by_app(samples: list[ProcessSample], cpu_count: int, per_resource: int) -> list[AppUsage]:
    """Add up processes with the same name, then keep the heaviest apps.

    We keep the top `per_resource` apps by CPU, by RAM and by I/O, merged,
    so each kind of hog gets caught.
    """
    totals: dict[str, AppUsage] = {}
    for s in samples:
        app = totals.setdefault(s.name, AppUsage(s.name, 0.0, 0.0, 0.0))
        app.cpu_percent += s.cpu_percent / cpu_count  # turn "% of one core" into "% of the machine"
        app.ram_mb += s.ram_bytes / MB
        app.io_mb_s += s.io_bytes_per_s / MB

    apps = list(totals.values())
    keep: dict[str, AppUsage] = {}
    for key in (lambda a: a.cpu_percent, lambda a: a.ram_mb, lambda a: a.io_mb_s):
        for app in sorted(apps, key=key, reverse=True)[:per_resource]:
            if key(app) > 0:
                keep[app.name] = app
    return sorted(keep.values(), key=lambda a: a.cpu_percent, reverse=True)


def disk_latency_ms(prev, cur) -> float | None:
    """Average ms per disk read/write between two psutil disk counter readings.

    This is "how long did each disk request wait", a waiting signal that works
    on both Windows and Ubuntu. Under ~10 ms is fine, over ~20 ms feels slow.
    None when the disk did nothing (there's no wait to measure).
    """
    ops = (cur.read_count - prev.read_count) + (cur.write_count - prev.write_count)
    if ops <= 0:
        return None
    busy_ms = (cur.read_time - prev.read_time) + (cur.write_time - prev.write_time)
    return max(busy_ms, 0) / ops


def system_drive() -> str:
    return os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"


class Sampler:
    """Reads one snapshot. Keeps the previous readings, because most numbers are
    rates ("MB/s since last time"), not totals."""

    def __init__(self, probe: Probe, config: Config):
        self.probe = probe
        self.config = config
        self.cpu_count = psutil.cpu_count() or 1
        self._last_time = time.monotonic()
        self._last_disk = psutil.disk_io_counters()
        self._last_proc_io: dict[int, int] = {}
        # psutil reports CPU % "since the last call", so the first call only primes it.
        psutil.cpu_percent(None)
        self._process_samples(elapsed=1.0)

    def sample(self) -> Snapshot:
        now = time.monotonic()
        elapsed = max(now - self._last_time, 1e-6)
        self._last_time = now

        mem = psutil.virtual_memory()
        disk = psutil.disk_io_counters()
        prev_disk, self._last_disk = self._last_disk, disk

        snap = Snapshot(
            ts=time.time(),
            cpu_percent=psutil.cpu_percent(None),
            ram_percent=mem.percent,
            ram_available_mb=mem.available / MB,
            swap_percent=psutil.swap_memory().percent,
            disk_read_mb_s=(disk.read_bytes - prev_disk.read_bytes) / MB / elapsed if disk and prev_disk else 0.0,
            disk_write_mb_s=(disk.write_bytes - prev_disk.write_bytes) / MB / elapsed if disk and prev_disk else 0.0,
            disk_used_percent=psutil.disk_usage(system_drive()).percent,
            cpu_freq_mhz=self._cpu_freq(),
            temp_c=self.probe.temperature_c(),
            disk_latency_ms=disk_latency_ms(prev_disk, disk) if disk and prev_disk else None,
        )
        snap.battery_percent, snap.on_charger = self._battery()
        for name, value in self.probe.waiting_signals().items():
            setattr(snap, name, value)
        snap.apps = group_by_app(self._process_samples(elapsed), self.cpu_count, self.config.top_apps_per_resource)
        return snap

    def _battery(self) -> tuple[float | None, bool | None]:
        try:
            battery = psutil.sensors_battery()
        except Exception:
            return None, None
        if battery is None:  # a desktop, or the OS doesn't say
            return None, None
        return battery.percent, battery.power_plugged

    def _cpu_freq(self) -> float | None:
        try:
            freq = psutil.cpu_freq()
            return freq.current if freq else None
        except Exception:
            return None

    def _process_samples(self, elapsed: float) -> list[ProcessSample]:
        samples = []
        seen_io: dict[int, int] = {}
        # process_iter remembers processes between calls, which cpu_percent needs.
        for proc in psutil.process_iter(["name", "memory_info"]):
            if proc.pid == 0:  # Windows "System Idle Process" isn't a real app
                continue
            try:
                cpu = proc.cpu_percent(None)
                ram = proc.info["memory_info"].rss if proc.info["memory_info"] else 0
                disk_rate = 0.0
                try:
                    io = proc.io_counters()
                    io_total = io.read_bytes + io.write_bytes
                    seen_io[proc.pid] = io_total
                    if proc.pid in self._last_proc_io:
                        disk_rate = max(io_total - self._last_proc_io[proc.pid], 0) / elapsed
                except (psutil.AccessDenied, AttributeError):
                    pass  # some system processes hide their disk numbers
                samples.append(ProcessSample(proc.info["name"] or "unknown", cpu, ram, disk_rate))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self._last_proc_io = seen_io
        return samples


def heartbeat_lag_ms(scheduled: float, woke: float, interval_s: float) -> float | None:
    """How late we woke up, in ms. If the CPU is jammed, even our small loop gets
    its turn late, so this is a cheap "CPU waiting" signal that needs no admin.

    A huge lag (over 2 intervals) means the laptop was asleep or the clock jumped,
    and sleep isn't slowness, so we return None.
    """
    lag_s = woke - scheduled
    if lag_s > 2 * interval_s:
        return None
    return max(lag_s, 0.0) * 1000


class Collector:
    def __init__(self, sampler: Sampler, store, config: Config):
        self.sampler = sampler
        self.store = store
        self.config = config
        self.buffer: list[Snapshot] = []
        self.stop_event = threading.Event()

    def run(self) -> None:
        interval = self.config.snapshot_interval_s
        next_tick = time.monotonic()
        last_flush = next_tick
        last_hour = int(time.time() // 3600)
        try:
            while not self.stop_event.is_set():
                next_tick += interval
                wait = next_tick - time.monotonic()
                if wait > 0:
                    self.stop_event.wait(wait)  # a sleep that stop() can interrupt
                woke = time.monotonic()
                lag = heartbeat_lag_ms(next_tick, woke, interval)
                # Count from now, not from the missed time. Otherwise after one long
                # stall the missed ticks run back to back and each looks late too.
                next_tick = max(next_tick, woke)

                snap = self.sampler.sample()
                snap.heartbeat_lag_ms = lag
                self.buffer.append(snap)

                if woke - last_flush >= self.config.flush_interval_s:
                    self.flush()
                    last_flush = woke

                hour = int(time.time() // 3600)
                if hour != last_hour:  # once an hour: summarise and delete old rows
                    self.flush()
                    self.store.summarize_and_prune(time.time(), self.config)
                    last_hour = hour
        finally:
            self.flush()

    def flush(self) -> None:
        if self.buffer:
            self.store.save(self.buffer)
            self.buffer = []

    def stop(self) -> None:
        self.stop_event.set()
