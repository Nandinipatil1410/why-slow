"""Stage 2: find the slow stretch, and when its cause started building up.

Two methods:
- hysteresis: a stretch starts when the score goes above 40 and only ends
  when it drops below 20. Two limits instead of one stop a score hovering
  around 30 from splitting into many tiny stretches.
  On top of that, stretches less than a minute apart are joined (one bad
  minute, not five alerts), and a single slow snapshot on its own is dropped
  as a blip. A frozen window always counts, even for one snapshot.
- change point: slowness often comes after the cause. RAM fills for a few
  minutes before things freeze. So we look back before the stretch and find
  the moment a usage number shifted the most (the split that best divides
  "before" from "after"). That's the "started building up at" time.
"""

from collections import Counter
from dataclasses import dataclass

from .score import Moment

ENTER, EXIT = 40.0, 20.0
JOIN_GAP_S = 60.0
MIN_MOMENTS = 2


@dataclass
class Episode:
    start: float
    end: float
    peak: float
    avg: float
    resource: str  # the resource that was waited on most
    moments: list[Moment]

    @property
    def minutes(self) -> float:
        return (self.end - self.start) / 60


def find_episodes(moments: list[Moment], max_gap_s: float = 15.0) -> list[Episode]:
    episodes, current = [], []
    for m in moments:
        if current:
            gap = m.ts - current[-1].ts
            if m.score < EXIT or gap > max_gap_s + 5:
                episodes.append(_make_episode(current))
                current = []
        if not current and m.score >= ENTER:
            current = [m]
        elif current:
            current.append(m)
    if current:
        episodes.append(_make_episode(current))
    return _join_and_drop_blips(episodes)


def _join_and_drop_blips(episodes: list[Episode]) -> list[Episode]:
    joined: list[Episode] = []
    for e in episodes:
        if joined and e.start - joined[-1].end <= JOIN_GAP_S:
            e = _make_episode(joined.pop().moments + e.moments)
        joined.append(e)
    return [e for e in joined if len(e.moments) >= MIN_MOMENTS or e.resource == "frozen"]


def _make_episode(moments: list[Moment]) -> Episode:
    resources = Counter(m.resource for m in moments if m.resource)
    return Episode(
        start=moments[0].ts,
        end=moments[-1].ts,
        peak=max(m.score for m in moments),
        avg=sum(m.score for m in moments) / len(moments),
        resource=resources.most_common(1)[0][0] if resources else "cpu",
        moments=moments,
    )


def pick_episode(episodes: list[Episode], at: float | None) -> Episode | None:
    """The stretch that contains `at`, else the closest one, else the worst one."""
    if not episodes:
        return None
    if at is None:
        return max(episodes, key=lambda e: e.peak * e.minutes ** 0.5)
    for e in episodes:
        if e.start <= at <= e.end:
            return e
    return min(episodes, key=lambda e: min(abs(e.start - at), abs(e.end - at)))


def change_point(values: list[float]) -> int | None:
    """Index where the series shifts most: the split that makes the two halves'
    averages most different, weighted by their sizes (a one-change least-squares
    fit). Returns None if there's no real shift."""
    n = len(values)
    if n < 4:
        return None
    total = sum(values)
    best_i, best_gain, left = None, 0.0, 0.0
    for i in range(1, n):
        left += values[i - 1]
        right = total - left
        gain = i * (n - i) / n * (left / i - right / (n - i)) ** 2
        if gain > best_gain:
            best_i, best_gain = i, gain
    mean = total / n
    variance = sum((v - mean) ** 2 for v in values) / n
    # Only trust it if the shift explains a good part of the variation.
    if best_i is None or variance == 0 or best_gain / (n * variance) < 0.3:
        return None
    return best_i
