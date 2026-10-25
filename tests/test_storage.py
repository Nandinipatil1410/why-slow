import sqlite3

from whyslow.config import Config
from whyslow.models import AppUsage, Snapshot
from whyslow.storage import DAY, HOUR, Store


def snap(ts, cpu=10.0, apps=None, hung=None):
    return Snapshot(
        ts=ts,
        cpu_percent=cpu,
        ram_percent=50,
        ram_available_mb=4000,
        swap_percent=0,
        disk_read_mb_s=1,
        disk_write_mb_s=1,
        disk_used_percent=60,
        heartbeat_lag_ms=5,
        foreground_app="code.exe" if hung is not None else None,
        foreground_hung=hung,
        apps=apps or [],
    )


def test_save_and_load_round_trip():
    store = Store(":memory:")
    original = snap(1000.0, apps=[AppUsage("chrome", 30, 1500, 0.5)], hung=True)
    store.save([original])
    [loaded] = store.snapshots_between(0, 2000)
    assert loaded == original


def test_hourly_summary_has_average_and_max():
    store = Store(":memory:")
    hour = 100 * HOUR
    store.save([snap(hour + 10, cpu=20), snap(hour + 20, cpu=60, hung=True)])
    store.summarize_and_prune(now=hour + 2 * HOUR, config=Config())
    row = store.db.execute("SELECT samples, hung_samples, cpu_percent_avg, cpu_percent_max FROM hourly_system").fetchone()
    assert row == (2, 1, 40.0, 60.0)


def test_unfinished_hour_is_not_summarised_yet():
    store = Store(":memory:")
    hour = 100 * HOUR
    store.save([snap(hour + 10)])
    store.summarize_and_prune(now=hour + 600, config=Config())
    assert store.counts()["hourly_system"] == 0


def test_old_detail_is_deleted_but_summary_kept():
    store = Store(":memory:")
    old = 1000 * HOUR
    store.save([snap(old + 10, apps=[AppUsage("chrome", 30, 1500, 0.5)])])
    store.summarize_and_prune(now=old + 8 * DAY, config=Config())
    counts = store.counts()
    assert counts["snapshots"] == 0 and counts["app_usage"] == 0
    assert counts["hourly_system"] == 1 and counts["hourly_apps"] == 1


def test_summaries_older_than_90_days_are_deleted():
    store = Store(":memory:")
    old = 1000 * HOUR
    store.save([snap(old + 10)])
    store.summarize_and_prune(now=old + 2 * HOUR, config=Config())
    store.summarize_and_prune(now=old + 91 * DAY, config=Config())
    assert store.counts()["hourly_system"] == 0


def test_battery_round_trip():
    store = Store(":memory:")
    original = snap(1000.0)
    original.battery_percent, original.on_charger = 64.0, False
    store.save([original])
    [loaded] = store.snapshots_between(0, 2000)
    assert loaded.battery_percent == 64.0 and loaded.on_charger is False


def test_old_database_gets_new_columns(tmp_path):
    # A database from before battery recording existed.
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE snapshots (ts REAL PRIMARY KEY, cpu_percent REAL)")
    db.execute("INSERT INTO snapshots VALUES (1000, 12)")
    db.commit()
    db.close()
    store = Store(path)
    columns = {row[1] for row in store.db.execute("PRAGMA table_info(snapshots)")}
    assert {"battery_percent", "on_charger"} <= columns
    assert store.db.execute("SELECT cpu_percent FROM snapshots").fetchone() == (12,)  # history kept
