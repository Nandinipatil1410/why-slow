"""Command line entry point.

    python -m whyslow collect    run the collector until Ctrl+C
    python -m whyslow web        open the timeline page in your browser
    python -m whyslow explain    explain the worst slowdown in the last hour
    python -m whyslow explain --at 14:41   explain the slowdown around 2:41 pm today
    python -m whyslow snapshot   print one snapshot, to check things work
    python -m whyslow status     show how much data is stored

Add --demo to `web` or `explain` to use a fake day of data instead of yours.
"""

import argparse
import dataclasses
import json
import signal
import time
import webbrowser

from .analyzer import explain
from .collector import Collector, Sampler
from .config import Config, default_data_dir
from .platforms import get_probe
from .storage import Store


def demo_config() -> Config:
    """A separate database filled with a fake day, rebuilt each time so it's always 'today'."""
    from . import demo

    config = Config(data_dir=default_data_dir() / "demo")
    config.db_path.unlink(missing_ok=True)
    store = Store(config.db_path)
    demo.build(store, time.time(), config)
    store.close()
    return config


def main() -> None:
    parser = argparse.ArgumentParser(prog="whyslow", description="Find out why your laptop is slow.")
    parser.add_argument("command", choices=["collect", "web", "explain", "snapshot", "status"])
    parser.add_argument("--at", help="time today to explain, like 14:41")
    parser.add_argument("--demo", action="store_true", help="use a fake day of data")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    config = demo_config() if args.demo else Config()

    if args.command == "explain":
        at = None
        if args.at:
            hour, minute = (int(x) for x in args.at.split(":"))
            today = time.localtime()
            at = time.mktime(today[:3] + (hour, minute, 0) + today[6:])
        print(explain(Store(config.db_path), at=at).text())

    elif args.command == "web":
        from .web import serve

        server = serve(args.port, config)
        url = f"http://127.0.0.1:{args.port}"
        print(f"Open {url} (Ctrl+C to stop)")
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()

    elif args.command == "snapshot":
        sampler = Sampler(get_probe(), config)
        time.sleep(1)  # rates need a gap between two readings
        print(json.dumps(dataclasses.asdict(sampler.sample()), indent=2))

    elif args.command == "status":
        store = Store(config.db_path)
        print(f"Database: {config.db_path}")
        print(f"Size: {config.db_path.stat().st_size / 1024 / 1024:.1f} MB")
        for table, count in store.counts().items():
            print(f"{table}: {count} rows")

    elif args.command == "collect":
        store = Store(config.db_path)
        collector = Collector(Sampler(get_probe(), config), store, config)
        signal.signal(signal.SIGINT, lambda *_: collector.stop())
        signal.signal(signal.SIGTERM, lambda *_: collector.stop())
        print(f"Collecting every {config.snapshot_interval_s:g} s into {config.db_path}. Ctrl+C to stop.")
        collector.run()
        store.close()


if __name__ == "__main__":
    main()
