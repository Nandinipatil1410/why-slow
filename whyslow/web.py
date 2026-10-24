"""The local web page: a timeline you can click to get an explanation.

Uses only Python's built-in web server, so there's nothing extra to install.
It listens on 127.0.0.1 only, so nothing on your network can see it.

    GET  /                       the page
    GET  /api/info               is this demo data?
    GET  /api/timeline?hours=24  slowness score per minute
    GET  /api/explain?at=<ts>    explanation for a moment (no `at` = worst in the last hour)
    POST /api/feedback           👍/👎 on an explanation
"""

import dataclasses
import json
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from .analyzer import explain
from .analyzer.score import score_snapshot
from .config import Config
from .storage import Store


def timeline(store: Store, hours: float, now: float) -> list[dict]:
    """One point per minute: the worst slowness score in that minute, plus
    average CPU and RAM so the page can show what was busy."""
    snaps = store.snapshots_between(now - hours * 3600, now + 1, with_apps=False)
    minutes: dict[int, dict] = {}
    for s in snaps:
        m = score_snapshot(s)
        key = int(s.ts // 60) * 60
        point = minutes.setdefault(key, {"ts": key, "score": 0.0, "resource": None, "cpu": 0.0, "ram": 0.0, "n": 0})
        if m.score > point["score"]:
            point["score"], point["resource"] = m.score, m.resource
        point["cpu"] += s.cpu_percent
        point["ram"] += s.ram_percent
        point["n"] += 1
    for point in minutes.values():
        point["cpu"] = round(point["cpu"] / point["n"], 1)
        point["ram"] = round(point["ram"] / point["n"], 1)
        del point["n"]
    return sorted(minutes.values(), key=lambda p: p["ts"])


class Handler(BaseHTTPRequestHandler):
    config = Config()
    demo = False

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            page = resources.files("whyslow").joinpath("static/index.html").read_bytes()
            return self._send(200, page, "text/html; charset=utf-8")
        if url.path == "/api/info":
            return self._json({"demo": self.demo})
        if url.path == "/api/timeline":
            hours = min(float(query.get("hours", ["24"])[0]), 24 * 7)
            with self._store() as store:
                return self._json(timeline(store, hours, time.time()))
        if url.path == "/api/explain":
            at = float(query["at"][0]) if "at" in query else None
            with self._store() as store:
                e = explain(store, at=at)
            return self._json({**dataclasses.asdict(e), "text": e.text()})
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if urlparse(self.path).path != "/api/feedback":
            return self._send(404, b"Not found", "text/plain")
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        with self._store() as store:
            store.save_feedback(
                float(body["start"]), float(body["end"]), body.get("cause"), body.get("culprit"), bool(body["helpful"])
            )
        self._json({"ok": True})

    @contextmanager
    def _store(self):
        # One connection per request: SQLite connections can't be shared between threads.
        store = Store(self.config.db_path)
        try:
            yield store
        finally:
            store.close()

    def _json(self, data):
        self._send(200, json.dumps(data).encode(), "application/json")

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the terminal quiet


def serve(port: int = 8765, config: Config | None = None, demo: bool = False) -> ThreadingHTTPServer:
    if config:
        Handler.config = config
    Handler.demo = demo
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
