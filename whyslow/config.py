"""Every setting the app uses, in one place.

Each value here was a design decision. See docs/DESIGN.md for the reasoning.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


def default_data_dir() -> Path:
    """Where the database lives: the usual per-user app data folder on each OS."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "whyslow"


@dataclass(frozen=True)
class Config:
    # Decision 2: one snapshot every 5 s catches freezes you notice, at under 1% CPU.
    snapshot_interval_s: float = 5.0
    # Decision 2 said "top 10 apps". We keep the top 5 by CPU, by RAM and by disk,
    # so a disk hog isn't missed just because it uses little CPU. Usually ~10 apps total.
    top_apps_per_resource: int = 5
    # Decision 3: keep snapshots in memory and write them in one batch per minute,
    # so the disk isn't touched every 5 s.
    flush_interval_s: float = 60.0
    # Decision 3: full detail for 7 days, hourly summaries for 90 days.
    full_detail_days: int = 7
    summary_days: int = 90
    data_dir: Path = field(default_factory=default_data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "whyslow.db"
