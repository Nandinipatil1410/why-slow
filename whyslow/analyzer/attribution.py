"""Stage 3: which app caused it, how much, and would removing it have helped?

Borrowed from Microsoft's Adtributor (used to debug Bing ad revenue drops):
- explanatory power: what share of the total rise this app accounts for.
  "Chrome added 1.9 GB of the 2.4 GB rise" = 79%.
- surprise: how unusual this is for THIS app, measured against its own normal
  (median and spread of past hourly averages). A robust z-score: how many
  "normal spreads" above its usual level it is.

An app that's big but always this big (low surprise) isn't the story.
An app that's unusual but tiny (low power) isn't either. We want both.

Then a what-if: take the culprit's extra usage away and recompute the total.
If the laptop would have been comfortable, the culprit really was the cause.
If not, the laptop is simply short on RAM/CPU for this workload.
"""

import statistics
from dataclasses import dataclass

from ..config import Config
from ..models import Snapshot

DAY = 86400

# Which per-app number matters for each kind of waiting.
METRIC = {"memory": "ram_mb", "cpu": "cpu_percent", "disk": "io_mb_s", "frozen": "cpu_percent"}
HOURLY_COLUMN = {"ram_mb": "ram_avg", "cpu_percent": "cpu_avg", "io_mb_s": "io_avg"}
# The smallest "normal spread" we allow, so a perfectly steady app isn't
# flagged as hugely surprising over a tiny change.
MIN_SPREAD = {"ram_mb": 100.0, "cpu_percent": 10.0, "io_mb_s": 2.0}
# Below these, the laptop feels fine (used by the what-if).
COMFORTABLE = {"ram_mb": 80.0, "cpu_percent": 70.0}

MIN_BASELINE_HOURS = 12  # cold start: fewer hours than this, use the minutes before instead
# Per-app I/O includes cached reads that never touch the disk (see models.py),
# so we only blame an app for a disk slowdown if the disk itself was busy.
MIN_DISK_MB_S = 1.0


@dataclass
class Suspect:
    name: str
    level: float  # average during the slow stretch
    normal: float  # its usual level
    excess: float  # level - normal (never below 0)
    power: float  # share of the total rise, 0-1
    surprise: float  # how many normal spreads above usual
    baseline: str  # "history" or "just before" (cold start)

    @property
    def score(self) -> float:
        return self.power * min(self.surprise / 3, 1.0)


@dataclass
class WhatIf:
    metric: str
    actual_percent: float  # machine-wide RAM % or CPU % during the stretch
    without_percent: float  # same, if the culprit had behaved normally
    comfortable: bool  # would that have been fine?


def app_levels(snaps: list[Snapshot], metric: str) -> dict[str, float]:
    """Average per app over the snapshots (missing from a snapshot counts as 0)."""
    totals: dict[str, float] = {}
    for s in snaps:
        for a in s.apps:
            totals[a.name] = totals.get(a.name, 0.0) + getattr(a, metric)
    return {name: total / len(snaps) for name, total in totals.items()} if snaps else {}


def levels_before(snaps: list[Snapshot], metric: str, names) -> dict[str, float]:
    """Like app_levels, for the minutes before a slowdown.

    We only save the top apps, so an app missing from a snapshot wasn't idle,
    just smaller than the last one saved. Here we count it at that size (the
    most it could have been), so a 900 MB app that just crept into the top list
    doesn't look like it came from nothing."""
    if not snaps:
        return {}
    totals = dict.fromkeys(names, 0.0)
    for s in snaps:
        values = {a.name: getattr(a, metric) for a in s.apps}
        ranked = sorted(values.values(), reverse=True)
        cutoff = ranked[Config.top_apps_per_resource - 1] if len(ranked) >= Config.top_apps_per_resource else 0.0
        for name in totals:
            totals[name] += values.get(name, cutoff)
    return {name: total / len(snaps) for name, total in totals.items()}


def history_baseline(store, name: str, metric: str, before: float) -> tuple[float, float] | None:
    """The app's normal level and spread from the last 7 days of hourly summaries."""
    column = HOURLY_COLUMN[metric]
    rows = store.db.execute(
        f"SELECT {column} FROM hourly_apps WHERE name = ? AND hour_ts >= ? AND hour_ts < ?",
        (name, before - 7 * DAY, before - 3600),
    ).fetchall()
    values = [r[0] for r in rows if r[0] is not None]
    if len(values) < MIN_BASELINE_HOURS:
        return None
    q1, median, q3 = statistics.quantiles(values, n=4)
    return median, q3 - q1


def find_suspects(store, during: list[Snapshot], before: list[Snapshot], resource: str) -> list[Suspect]:
    metric = METRIC[resource]
    if resource == "disk":
        disk_mb_s = sum(s.disk_read_mb_s + s.disk_write_mb_s for s in during) / len(during)
        if disk_mb_s < MIN_DISK_MB_S:
            return []  # the disk was slow but barely used: no app to blame
    now_levels = app_levels(during, metric)
    before_levels = levels_before(before, metric, now_levels)
    start = during[0].ts

    rows = []
    for name, level in now_levels.items():
        hist = history_baseline(store, name, metric, start)
        if hist:
            normal, spread = hist
            source = "history"
        else:
            normal, spread = before_levels.get(name, 0.0), 0.0
            source = "just before"
        spread = max(spread, MIN_SPREAD[metric])
        excess = max(level - normal, 0.0)
        rows.append((name, level, normal, excess, excess / spread, source))

    total_excess = sum(r[3] for r in rows)
    suspects = [
        Suspect(name, level, normal, excess, excess / total_excess if total_excess else 0.0, surprise, source)
        for name, level, normal, excess, surprise, source in rows
    ]
    suspects = [s for s in suspects if s.power >= 0.1 and s.surprise >= 1.0]
    return sorted(suspects, key=lambda s: s.score, reverse=True)


def what_if(during: list[Snapshot], culprit: Suspect, resource: str) -> WhatIf | None:
    """Recompute the machine-wide number without the culprit's extra usage.

    Exact for RAM (memory adds up). Only rough for CPU, because a busy CPU
    also slows the apps that are waiting. Not attempted for disk."""
    metric = METRIC[resource]
    if metric == "ram_mb":
        totals = [s.ram_available_mb / (1 - s.ram_percent / 100) for s in during if s.ram_percent < 100]
        if not totals:
            return None
        total_mb = sum(totals) / len(totals)
        actual = sum(s.ram_percent for s in during) / len(during)
        without = actual - culprit.excess / total_mb * 100
    elif metric == "cpu_percent":
        actual = sum(s.cpu_percent for s in during) / len(during)
        without = actual - culprit.excess
    else:
        return None
    without = max(without, 0.0)
    return WhatIf(metric, actual, without, without < COMFORTABLE[metric])
