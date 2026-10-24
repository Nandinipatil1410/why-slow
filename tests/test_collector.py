from collections import namedtuple

import pytest

from whyslow.collector import ProcessSample, disk_latency_ms, group_by_app, heartbeat_lag_ms

Disk = namedtuple("Disk", "read_count write_count read_time write_time")


def test_processes_with_same_name_are_added_up():
    samples = [
        ProcessSample("chrome", cpu_percent=100, ram_bytes=500 * 1024 * 1024, io_bytes_per_s=0),
        ProcessSample("chrome", cpu_percent=100, ram_bytes=500 * 1024 * 1024, io_bytes_per_s=0),
        ProcessSample("code", cpu_percent=50, ram_bytes=200 * 1024 * 1024, io_bytes_per_s=0),
    ]
    apps = group_by_app(samples, cpu_count=4, per_resource=5)
    chrome = next(a for a in apps if a.name == "chrome")
    assert chrome.cpu_percent == 50  # 200% of one core = 50% of a 4-core machine
    assert chrome.ram_mb == 1000


def test_a_disk_hog_is_kept_even_with_low_cpu():
    samples = [ProcessSample(f"busy{i}", cpu_percent=90 - i, ram_bytes=0, io_bytes_per_s=0) for i in range(5)]
    samples.append(ProcessSample("backup", cpu_percent=1, ram_bytes=0, io_bytes_per_s=50 * 1024 * 1024))
    names = {a.name for a in group_by_app(samples, cpu_count=1, per_resource=5)}
    assert "backup" in names


def test_idle_apps_are_dropped():
    samples = [ProcessSample("sleepy", cpu_percent=0, ram_bytes=0, io_bytes_per_s=0)]
    assert group_by_app(samples, cpu_count=1, per_resource=5) == []


def test_disk_latency_is_time_per_request():
    before = Disk(read_count=100, write_count=100, read_time=1000, write_time=1000)
    after = Disk(read_count=110, write_count=110, read_time=1200, write_time=1200)
    assert disk_latency_ms(before, after) == 20  # 400 ms over 20 requests


def test_disk_latency_is_none_when_disk_is_idle():
    same = Disk(1, 1, 1, 1)
    assert disk_latency_ms(same, same) is None


def test_heartbeat_lag():
    assert heartbeat_lag_ms(scheduled=100.0, woke=100.4, interval_s=5) == pytest.approx(400)
    assert heartbeat_lag_ms(scheduled=100.0, woke=99.99, interval_s=5) == 0


def test_heartbeat_ignores_laptop_sleep():
    # Woke 10 minutes late: the lid was closed, not a slowdown.
    assert heartbeat_lag_ms(scheduled=100.0, woke=700.0, interval_s=5) is None
