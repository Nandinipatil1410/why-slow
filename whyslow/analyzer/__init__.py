"""The analyzer: explains one slow moment in plain words, without any AI model.

    explain(store, at=None) -> Explanation

Pipeline (see docs/DESIGN.md):
1. score.py        how slow each moment felt, from "waiting" signals
2. episodes.py     the slow stretch, and when its cause started building up
3. attribution.py  which app caused how much, plus a what-if
4. story.py        the sentences and one action
"""

import time
from collections import Counter

from .attribution import METRIC, find_suspects, what_if
from .episodes import change_point, find_episodes, pick_episode
from .score import score_snapshot
from .story import (
    Explanation,
    choose_cause,
    clock,
    culprit_sentence,
    friendly,
    headline,
    waiting_sentence,
    what_if_sentence,
)

LOOK_AROUND_S = 30 * 60
BEFORE_S = 10 * 60


def explain(store, at: float | None = None, now: float | None = None) -> Explanation:
    """Explain the slowdown at time `at`, or the worst one in the last hour."""
    now = now or time.time()
    start, end = (at - LOOK_AROUND_S, at + LOOK_AROUND_S) if at else (now - 2 * LOOK_AROUND_S, now)
    snaps = store.snapshots_between(start - BEFORE_S, end)
    window = [s for s in snaps if s.ts >= start]

    ep = pick_episode(find_episodes([score_snapshot(s) for s in window]), at)
    if ep is None:
        where = "around that time" if at else "in the last hour"
        return Explanation(found=False, headline=f"No slowdown found {where}. The laptop was running smoothly.")

    during = [s for s in snaps if ep.start <= s.ts <= ep.end]
    before = [s for s in snaps if ep.start - BEFORE_S <= s.ts < ep.start]

    culprit, whatif, culprit_name = None, None, None
    if ep.resource == "frozen":
        # The frozen window names the culprit directly.
        hung_apps = Counter(s.foreground_app for s in during if s.foreground_hung and s.foreground_app)
        if hung_apps:
            culprit_name = hung_apps.most_common(1)[0][0]
    else:
        suspects = find_suspects(store, during, before, ep.resource)
        culprit = suspects[0] if suspects else None
        culprit_name = culprit.name if culprit else None
        if culprit:
            whatif = what_if(during, culprit, ep.resource)

    details = []
    if ep.resource == "frozen":
        app = friendly(culprit_name) if culprit_name else "The app you were using"
        details.append(f"{app} stopped responding (Windows marked it \"Not Responding\").")
    elif sentence := waiting_sentence(ep, during):
        details.append(sentence)

    buildup = _buildup_time(before + during, ep.resource)
    if buildup is not None and buildup < ep.start - 30:
        details.append(f"It started building up at {clock(buildup)}, a few minutes before it felt slow.")

    if culprit:
        details.append(culprit_sentence(culprit, METRIC[ep.resource]))
    if whatif:
        details.append(what_if_sentence(whatif))

    cause, action = choose_cause(ep, during, culprit_name, whatif, _freq_drop(before + during))
    return Explanation(
        found=True,
        headline=headline(ep),
        details=details,
        action=action,
        cause=cause,
        culprit=culprit_name,
        start=ep.start,
        end=ep.end,
        resource=ep.resource,
    )


def _buildup_time(snaps, resource: str) -> float | None:
    """When the machine-wide usage number for this resource shifted (stage 2's change point)."""
    pick = {
        "memory": lambda s: s.ram_percent,
        "cpu": lambda s: s.cpu_percent,
        "disk": lambda s: s.disk_read_mb_s + s.disk_write_mb_s,
    }.get(resource)
    if pick is None or not snaps:
        return None
    i = change_point([pick(s) for s in snaps])
    return snaps[i].ts if i is not None else None


def _freq_drop(snaps) -> float | None:
    """How far the CPU speed fell below its best in this window (0.4 = 40% slower)."""
    freqs = [s.cpu_freq_mhz for s in snaps if s.cpu_freq_mhz]
    if len(freqs) < 4:
        return None
    recent = freqs[-len(freqs) // 3 :]
    return 1 - (sum(recent) / len(recent)) / max(freqs)
