"""The analyzer, tested on made-up but realistic slowdowns."""

from whyslow.analyzer import explain
from whyslow.analyzer.episodes import change_point, find_episodes
from whyslow.analyzer.score import Moment, score_snapshot
from whyslow.models import AppUsage, Snapshot
from whyslow.storage import HOUR, Store

T = 1_000 * HOUR + 1800  # the moment the user clicks on
TOTAL_MB = 8192
OTHER_MB = 3500  # everything except Chrome


def make_snap(ts, chrome_mb=1200.0, mem_pressure=0.0, **extra):
    used = OTHER_MB + chrome_mb
    pct = used / TOTAL_MB * 100
    fields = dict(
        ts=ts,
        cpu_percent=20,
        ram_percent=pct,
        ram_available_mb=TOTAL_MB - used,
        swap_percent=0,
        disk_read_mb_s=1,
        disk_write_mb_s=1,
        disk_used_percent=60,
        heartbeat_lag_ms=5,
        mem_pressure=mem_pressure,
        apps=[AppUsage("chrome", 10, chrome_mb, 0.1), AppUsage("code", 5, 500, 0.1)],
    )
    fields.update(extra)
    return Snapshot(**fields)


def add_history(store, hours=48):
    """Two days of normal hourly numbers: Chrome usually ~1.2 GB."""
    with store.db:
        for h in range(1, hours + 1):
            hour_ts = int(T // HOUR) * HOUR - h * HOUR
            store.db.execute(
                "INSERT INTO hourly_apps VALUES (?, 'chrome', 720, 10, 20, ?, ?, 0.1, 1)",
                (hour_ts, 1150 + (h % 5) * 25, 1400),
            )
            store.db.execute("INSERT INTO hourly_apps VALUES (?, 'code', 720, 5, 10, 500, 520, 0.1, 1)", (hour_ts,))


def chrome_leak_store(with_history=True):
    """Chrome grows from 1.2 GB to 3.1 GB over 8 minutes, the laptop chokes for ~10 min."""
    store = Store(":memory:")
    if with_history:
        add_history(store)
    snaps = []
    for ts in range(int(T - 40 * 60), int(T + 20 * 60), 5):
        if ts < T - 10 * 60:
            chrome = 1200.0
        elif ts < T - 2 * 60:
            chrome = 1200 + (ts - (T - 10 * 60)) / (8 * 60) * 1900
        elif ts < T + 8 * 60:
            chrome = 3100.0
        else:
            chrome = 1200.0
        pressure = 35.0 if T - 2 * 60 <= ts < T + 8 * 60 else 0.0
        snaps.append(make_snap(float(ts), chrome, pressure))
    store.save(snaps)
    return store


def test_score_picks_worst_waiting_signal():
    m = score_snapshot(make_snap(0, mem_pressure=40, disk_latency_ms=15))
    assert m.resource == "memory" and m.score == 100


def test_frozen_window_is_always_slow():
    m = score_snapshot(make_snap(0, foreground_hung=True))
    assert m.resource == "frozen" and m.score == 100


def test_episode_does_not_split_on_small_dips():
    scores = [0, 50, 60, 30, 55, 10, 0]  # 30 is below "enter" but above "exit"
    moments = [Moment(i * 5.0, s, "cpu") for i, s in enumerate(scores)]
    [ep] = find_episodes(moments)
    assert ep.start == 5 and ep.end == 20


def test_change_point_finds_the_shift():
    assert change_point([1, 1, 1, 1, 9, 9, 9, 9]) == 4
    assert change_point([5, 5, 5, 5, 5, 5]) is None


def test_chrome_memory_leak_is_explained():
    e = explain(chrome_leak_store(), at=T)
    assert e.found
    assert e.resource == "memory"
    assert e.culprit == "chrome"
    assert e.cause == "app_memory"
    text = e.text()
    assert "Google Chrome" in text
    assert "when it normally uses about 1.2 GB" in text
    assert "would have felt smooth" in text  # the what-if says Chrome was the real cause
    assert "started building up" in text  # change point found the slow growth before the freeze
    assert "Try: Close the tabs" in text


def test_cold_start_compares_with_just_before():
    e = explain(chrome_leak_store(with_history=False), at=T)
    assert e.culprit == "chrome"
    assert "just before" in e.text()


def test_no_slowdown():
    store = Store(":memory:")
    store.save([make_snap(float(ts)) for ts in range(int(T - 600), int(T + 600), 5)])
    e = explain(store, at=T)
    assert not e.found
    assert "running smoothly" in e.headline


def test_ram_too_small_when_no_single_app_is_to_blame():
    store = Store(":memory:")
    add_history(store)
    # RAM is full and programs wait, but every app is at its usual size.
    store.save([make_snap(float(ts), 1200, mem_pressure=30) for ts in range(int(T - 900), int(T + 300), 5)])
    e = explain(store, at=T)
    assert e.found and e.cause == "ram_too_small"
    assert "adding RAM" in e.action


def test_frozen_app_on_windows():
    store = Store(":memory:")
    snaps = [
        make_snap(float(ts), foreground_app="WINWORD.EXE", foreground_hung=T <= ts < T + 30)
        for ts in range(int(T - 300), int(T + 300), 5)
    ]
    store.save(snaps)
    e = explain(store, at=T + 10)
    assert e.cause == "app_frozen" and e.culprit == "WINWORD.EXE"
    assert "stopped responding" in e.text()


def test_full_disk():
    store = Store(":memory:")
    store.save(
        [
            make_snap(float(ts), disk_latency_ms=80 if ts >= T else 3, disk_used_percent=96)
            for ts in range(int(T - 300), int(T + 300), 5)
        ]
    )
    e = explain(store, at=T + 60)
    assert e.cause == "disk_full"
    assert "96% full" in e.action


def test_cached_io_is_not_blamed_when_disk_was_idle():
    # Windows counts cached reads as app I/O. If the disk itself barely moved,
    # the app's big I/O number can't be the reason the disk was slow.
    store = Store(":memory:")
    indexer = AppUsage("SearchIndexer.exe", 3, 80, 90.0)
    store.save(
        [
            make_snap(float(ts), disk_latency_ms=80 if ts >= T else 3, disk_read_mb_s=0.1, disk_write_mb_s=0.1,
                      apps=[indexer] if ts >= T else [])
            for ts in range(int(T - 300), int(T + 300), 5)
        ]
    )
    e = explain(store, at=T + 60)
    assert e.cause == "slow_disk" and e.culprit is None
