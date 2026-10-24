"""Stage 4: turn the findings into a short story with one action.

This is classic "data-to-text" generation, the way medical and weather report
systems did it long before LLMs:
1. pick the facts worth saying (content selection)
2. put them in a fixed order: what, when, who, why, fix
3. fill sentence templates with human-friendly numbers

Every sentence comes from a number we measured, so it can't make things up.
"""

import json
import time
from dataclasses import dataclass, field
from importlib import resources

from .attribution import Suspect, WhatIf
from .episodes import Episode


def load_known_apps() -> dict:
    text = resources.files("whyslow").joinpath("data/known_apps.json").read_text(encoding="utf-8")
    return {k: v for k, v in json.loads(text).items() if not k.startswith("_")}


KNOWN_APPS = load_known_apps()


def known(app: str) -> dict | None:
    key = app.lower().removesuffix(".exe")
    return KNOWN_APPS.get(key)


def friendly(app: str) -> str:
    info = known(app)
    return info["name"] if info else app.removesuffix(".exe")


def clock(ts: float) -> str:
    t = time.localtime(ts)
    hour = t.tm_hour % 12 or 12
    return f"{hour}:{t.tm_min:02d} {'am' if t.tm_hour < 12 else 'pm'}"


def size(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def amount(metric: str, value: float) -> str:
    if metric == "ram_mb":
        return size(value)
    if metric == "cpu_percent":
        return f"{value:.0f}% of the CPU"
    return f"{value:.0f} MB/s of disk"


@dataclass
class Explanation:
    found: bool
    headline: str
    details: list[str] = field(default_factory=list)
    action: str | None = None
    cause: str | None = None  # a key like "app_memory", used later for 👍/👎 labels
    culprit: str | None = None
    start: float | None = None
    end: float | None = None
    resource: str | None = None

    def text(self) -> str:
        parts = [self.headline, *self.details]
        if self.action:
            parts.append(f"Try: {self.action}")
        return "\n\n".join(parts)


def headline(ep: Episode) -> str:
    if ep.minutes < 1:
        seconds = max(ep.end - ep.start, 5)
        return f"Your laptop was slow for about {seconds:.0f} seconds at {clock(ep.start)}."
    return f"Your laptop was slow from {clock(ep.start)} to {clock(ep.end)} ({ep.minutes:.0f} min)."


def waiting_sentence(ep: Episode, during) -> str | None:
    def avg(field_name):
        vals = [getattr(s, field_name) for s in during if getattr(s, field_name) is not None]
        return sum(vals) / len(vals) if vals else None

    if ep.resource == "memory":
        if (p := avg("mem_pressure")) is not None:
            return f"Programs were stuck waiting for memory {p:.0f}% of the time."
        if (f := avg("hard_faults_per_s")) is not None:
            return f"RAM was full, so Windows kept fetching memory back from the disk (about {f:.0f} times a second)."
        return "Programs were stuck waiting for memory."
    if ep.resource == "cpu":
        if (p := avg("cpu_pressure")) is not None and p >= 10:
            return f"Programs were waiting for the CPU {p:.0f}% of the time."
        if (lag := avg("heartbeat_lag_ms")) is not None:
            return f"The CPU was so busy that even small tasks ran about {lag:.0f} ms late."
        return "The CPU was too busy to keep up."
    if ep.resource == "disk":
        if (lat := avg("disk_latency_ms")) is not None:
            return f"Each disk request took about {lat:.0f} ms (under 10 ms is normal)."
        return "Programs were stuck waiting for the disk."
    return None


def culprit_sentence(s: Suspect, metric: str) -> str:
    if s.normal < {"ram_mb": 50, "cpu_percent": 1, "disk_mb_s": 1}[metric]:
        usual = "when it's normally almost idle" if s.baseline == "history" else "after being almost idle just before"
    elif s.baseline == "history":
        usual = f"when it normally uses about {amount(metric, s.normal)}"
    else:
        usual = f"up from about {amount(metric, s.normal)} just before"
    share = "almost all" if s.power >= 0.95 else f"about {s.power * 100:.0f}%"
    return (
        f"The main cause was {friendly(s.name)}, which used {amount(metric, s.level)}, {usual}. "
        f"That's {share} of the increase."
    )


def what_if_sentence(w: WhatIf) -> str:
    thing = "memory" if w.metric == "ram_mb" else "CPU"
    if w.comfortable:
        return (
            f"Without that extra, {thing} would have been around {w.without_percent:.0f}% "
            f"instead of {w.actual_percent:.0f}%, and things would have felt smooth."
        )
    return (
        f"Even without that extra, {thing} would have been at {w.without_percent:.0f}%, "
        f"so the laptop was short on {thing} overall, not just because of one app."
    )


def choose_cause(ep: Episode, during, name: str | None, whatif: WhatIf | None, freq_drop: float | None):
    """Pick the cause category and its action. Rules only live here, at the very end."""
    tip = known(name)["tip"] if name and known(name) else None

    if ep.resource == "frozen":
        app = friendly(name) if name else "The app you were using"
        return "app_frozen", f"If {app} freezes often, update or reinstall it. If it happens with every app, the laptop itself is overloaded."
    if ep.resource == "cpu" and freq_drop is not None and freq_drop >= 0.35:
        return "throttling", (
            f"The CPU slowed itself down by {freq_drop * 100:.0f}%, usually because it got too hot or a power-saving "
            "mode kicked in. Plug in the charger, check the power mode, and keep the air vents clear."
        )
    if ep.resource == "disk":
        full = max(s.disk_used_percent for s in during)
        if full >= 90:
            return "disk_full", f"Your system drive is {full:.0f}% full. Free up space; under 85% full keeps things fast."
        if name:
            return "app_disk", tip or f"{friendly(name)} was reading or writing a lot. If it's a sync or backup, schedule it for when you're away."
        return "slow_disk", "If this happens often, your drive may be an old hard drive. Switching to an SSD is the biggest speed-up for older laptops."
    if name and (whatif is None or whatif.comfortable):
        if ep.resource == "memory":
            return "app_memory", tip or f"Restart {friendly(name)}. If it grows slowly over hours, that's a memory leak, and a restart fixes it."
        return "app_cpu", tip or f"Close {friendly(name)} if you're not using it, or check if it's stuck on something."
    if ep.resource == "memory":
        return "ram_too_small", (
            "Your usual set of apps doesn't fit in RAM. Close a few when you need speed. "
            "If this happens every day, adding RAM helps more than a new laptop."
        )
    return "cpu_busy_many", "Several apps kept the CPU busy together. Close the ones you aren't using, or check what's set to start automatically."
