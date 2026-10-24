"""Saves snapshots in one SQLite file and keeps it small (decision 3).

Tables:
- snapshots:     one row per 5 s, laptop-wide numbers   (kept 7 days)
- app_usage:     the heavy apps in each snapshot         (kept 7 days)
- hourly_system: average + max of each number per hour   (kept 90 days)
- hourly_apps:   average + max per app per hour          (kept 90 days)

Old detail is rarely needed second by second ("was last Tuesday slow?" only needs
hourly numbers), so each hour we summarise, then delete detail older than 7 days.
This is called downsampling.
"""

import dataclasses
import sqlite3
import time
from pathlib import Path

from .config import Config
from .models import AppUsage, Snapshot

HOUR = 3600
DAY = 86400

# Snapshot columns, taken straight from the dataclass so the two can't drift apart.
COLUMNS = [f.name for f in dataclasses.fields(Snapshot) if f.name != "apps"]
TEXT_COLUMNS = {"foreground_app"}
# Columns that get an hourly average and max. ts is the key, and the
# foreground app/hung pair is summarised separately as a count of frozen samples.
SUMMARY_COLUMNS = [c for c in COLUMNS if c not in ("ts", "foreground_app", "foreground_hung")]


def _column_sql(name: str) -> str:
    if name == "ts":
        return "ts REAL PRIMARY KEY"
    return f"{name} {'TEXT' if name in TEXT_COLUMNS else 'REAL'}"


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS snapshots ({", ".join(_column_sql(c) for c in COLUMNS)});

CREATE TABLE IF NOT EXISTS app_usage (
    ts REAL NOT NULL,
    name TEXT NOT NULL,
    cpu_percent REAL,
    ram_mb REAL,
    io_mb_s REAL,
    PRIMARY KEY (ts, name)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS app_usage_by_name ON app_usage (name, ts);

CREATE TABLE IF NOT EXISTS hourly_system (
    hour_ts INTEGER PRIMARY KEY,
    samples INTEGER,
    hung_samples INTEGER,
    {", ".join(f"{c}_avg REAL, {c}_max REAL" for c in SUMMARY_COLUMNS)}
);

CREATE TABLE IF NOT EXISTS hourly_apps (
    hour_ts INTEGER NOT NULL,
    name TEXT NOT NULL,
    samples INTEGER,
    cpu_avg REAL, cpu_max REAL,
    ram_avg REAL, ram_max REAL,
    io_avg REAL, io_max REAL,
    PRIMARY KEY (hour_ts, name)
) WITHOUT ROWID;

-- 👍/👎 answers. Never deleted: they're the training data for a future model.
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    given_at REAL,
    start_ts REAL,
    end_ts REAL,
    cause TEXT,
    culprit TEXT,
    helpful INTEGER
);
"""


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        # WAL lets the web page read while the collector writes.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def save(self, snapshots: list[Snapshot]) -> None:
        """Write a batch of snapshots in one transaction (one disk write, not 12)."""
        placeholders = ", ".join("?" for _ in COLUMNS)
        with self.db:
            self.db.executemany(
                f"INSERT OR REPLACE INTO snapshots ({', '.join(COLUMNS)}) VALUES ({placeholders})",
                [tuple(getattr(s, c) for c in COLUMNS) for s in snapshots],
            )
            self.db.executemany(
                "INSERT OR REPLACE INTO app_usage VALUES (?, ?, ?, ?, ?)",
                [(s.ts, a.name, a.cpu_percent, a.ram_mb, a.io_mb_s) for s in snapshots for a in s.apps],
            )

    def snapshots_between(self, start: float, end: float, with_apps: bool = True) -> list[Snapshot]:
        """Load snapshots for a time window, oldest first. Skip the apps when you
        only need laptop-wide numbers (like the 24 h timeline): it's ~10x less data."""
        rows = self.db.execute(
            f"SELECT {', '.join(COLUMNS)} FROM snapshots WHERE ts >= ? AND ts < ? ORDER BY ts", (start, end)
        ).fetchall()
        snaps = {row[0]: Snapshot(**dict(zip(COLUMNS, row))) for row in rows}
        for snap in snaps.values():
            if snap.foreground_hung is not None:
                snap.foreground_hung = bool(snap.foreground_hung)
        if not with_apps:
            return list(snaps.values())
        for ts, name, cpu, ram, disk in self.db.execute(
            "SELECT ts, name, cpu_percent, ram_mb, io_mb_s FROM app_usage WHERE ts >= ? AND ts < ?", (start, end)
        ):
            if ts in snaps:
                snaps[ts].apps.append(AppUsage(name, cpu, ram, disk))
        for snap in snaps.values():
            snap.apps.sort(key=lambda a: a.cpu_percent, reverse=True)
        return list(snaps.values())

    def summarize_and_prune(self, now: float, config: Config) -> None:
        """Run once an hour: summarise every finished hour, then delete old rows."""
        current_hour = int(now // HOUR) * HOUR
        stats = ", ".join(f"AVG({c}), MAX({c})" for c in SUMMARY_COLUMNS)
        stat_names = ", ".join(f"{c}_avg, {c}_max" for c in SUMMARY_COLUMNS)
        with self.db:
            # Only look at hours after the last one we summarised, so this stays fast.
            self.db.execute(
                f"""INSERT OR IGNORE INTO hourly_system (hour_ts, samples, hung_samples, {stat_names})
                    SELECT CAST(ts / {HOUR} AS INTEGER) * {HOUR} AS h, COUNT(*),
                           SUM(COALESCE(foreground_hung, 0)), {stats}
                    FROM snapshots
                    WHERE ts < ? AND ts >= (SELECT COALESCE(MAX(hour_ts) + {HOUR}, 0) FROM hourly_system)
                    GROUP BY h""",
                (current_hour,),
            )
            self.db.execute(
                f"""INSERT OR IGNORE INTO hourly_apps
                    SELECT CAST(ts / {HOUR} AS INTEGER) * {HOUR} AS h, name, COUNT(*),
                           AVG(cpu_percent), MAX(cpu_percent), AVG(ram_mb), MAX(ram_mb),
                           AVG(io_mb_s), MAX(io_mb_s)
                    FROM app_usage
                    WHERE ts < ? AND ts >= (SELECT COALESCE(MAX(hour_ts) + {HOUR}, 0) FROM hourly_apps)
                    GROUP BY h, name""",
                (current_hour,),
            )
            detail_cutoff = now - config.full_detail_days * DAY
            summary_cutoff = now - config.summary_days * DAY
            self.db.execute("DELETE FROM snapshots WHERE ts < ?", (detail_cutoff,))
            self.db.execute("DELETE FROM app_usage WHERE ts < ?", (detail_cutoff,))
            self.db.execute("DELETE FROM hourly_system WHERE hour_ts < ?", (summary_cutoff,))
            self.db.execute("DELETE FROM hourly_apps WHERE hour_ts < ?", (summary_cutoff,))

    def save_feedback(self, start: float, end: float, cause: str | None, culprit: str | None, helpful: bool) -> None:
        """A 👍/👎 on an explanation. These become labelled examples for a v2 model."""
        with self.db:
            self.db.execute(
                "INSERT INTO feedback (given_at, start_ts, end_ts, cause, culprit, helpful) VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), start, end, cause, culprit, int(helpful)),
            )

    def counts(self) -> dict[str, int]:
        tables = ("snapshots", "app_usage", "hourly_system", "hourly_apps", "feedback")
        return {t: self.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
