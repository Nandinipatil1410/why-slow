"""Stage 1: how slow did the laptop feel at each moment?

Each waiting signal is turned into a 0-1 "badness" between two limits:
0 below `fine`, 1 above `bad`, a straight line in between. The moment's
slowness score is the worst one, times 100, and we remember which resource
it came from (cpu, memory, disk, or a frozen window).

The limits are starting guesses from common rules of thumb (for example disk
latency: under 10 ms is fine, over 20 ms is slow). They're meant to be tuned
with real data and the 👍/👎 feedback.
"""

from dataclasses import dataclass

from ..models import Snapshot


@dataclass(frozen=True)
class Signal:
    field: str
    resource: str  # "cpu", "memory", "disk" or "frozen"
    fine: float
    bad: float
    min_ram_percent: float = 0  # ignore this signal while RAM still has room


SIGNALS = [
    # Ubuntu's kernel pressure numbers: % of time something was stuck.
    Signal("cpu_pressure", "cpu", fine=10, bad=60),
    Signal("mem_pressure", "memory", fine=5, bad=40),
    Signal("io_pressure", "disk", fine=10, bad=60),
    # Both OSes.
    Signal("heartbeat_lag_ms", "cpu", fine=100, bad=1000),
    Signal("disk_latency_ms", "disk", fine=10, bad=60),
    # Windows. "Pages Input/sec" also counts normal file reads (apps opening
    # files through memory mapping), so on its own it isn't proof RAM is short.
    # On a real laptop it hit 3000+/s at 55% RAM with nothing slow, so we only
    # trust it once RAM is nearly full.
    Signal("hard_faults_per_s", "memory", fine=1000, bad=5000, min_ram_percent=80),
]


def badness(value: float | None, fine: float, bad: float) -> float:
    if value is None:
        return 0.0
    return min(max((value - fine) / (bad - fine), 0.0), 1.0)


@dataclass
class Moment:
    ts: float
    score: float  # 0 = smooth, 100 = very slow
    resource: str | None  # what the worst signal was waiting on


def score_snapshot(snap: Snapshot) -> Moment:
    worst, resource = 0.0, None
    for sig in SIGNALS:
        if snap.ram_percent < sig.min_ram_percent:
            continue
        b = badness(getattr(snap, sig.field), sig.fine, sig.bad)
        if b > worst:
            worst, resource = b, sig.resource
    if snap.foreground_hung:  # Windows says the window you're using is frozen
        worst, resource = 1.0, "frozen"
    return Moment(snap.ts, round(worst * 100, 1), resource)
