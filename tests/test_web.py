import json
import threading
import time
import urllib.request

from whyslow import demo
from whyslow.config import Config
from whyslow.storage import Store
from whyslow.web import serve, timeline

from test_storage import snap


def test_timeline_has_one_point_per_minute_and_shows_slowdowns(tmp_path):
    config = Config(data_dir=tmp_path)
    store = Store(config.db_path)
    now = time.time()
    demo.build(store, now, config)
    points = timeline(store, hours=24, now=now)
    assert 1430 <= len(points) <= 1441
    assert max(p["score"] for p in points) >= 70  # the demo has real slowdowns


def test_timeline_carries_battery_when_recorded():
    store = Store(":memory:")
    now = 10_000.0
    older, latest = snap(now - 120), snap(now - 30)
    latest.battery_percent, latest.on_charger = 64.0, False
    store.save([older, latest])
    points = timeline(store, hours=1, now=now)
    assert points[0]["battery"] is None  # older data, or a desktop
    assert (points[-1]["battery"], points[-1]["charging"]) == (64.0, False)


def test_api_explain_and_feedback(tmp_path):
    config = Config(data_dir=tmp_path)
    store = Store(config.db_path)
    now = time.time()
    demo.build(store, now, config)
    server = serve(0, config)  # port 0 = any free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        e = json.load(urllib.request.urlopen(f"{base}/api/explain?at={now - 5 * 3600}"))
        assert e["found"] and e["culprit"] == "chrome"

        body = json.dumps({"start": e["start"], "end": e["end"], "cause": e["cause"], "culprit": e["culprit"], "helpful": True})
        req = urllib.request.Request(f"{base}/api/feedback", data=body.encode(), headers={"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(req)) == {"ok": True}
        assert store.counts()["feedback"] == 1
    finally:
        server.shutdown()
