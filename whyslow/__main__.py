"""Command line entry point.

    python -m whyslow collect    run the collector until Ctrl+C
    python -m whyslow snapshot   print one snapshot, to check things work
    python -m whyslow status     show how much data is stored
    python -m whyslow explain    explain the worst slowdown in the last hour
    python -m whyslow explain --at 14:41   explain the slowdown around 2:41 pm today
"""

import argparse
import dataclasses
import json
import signal
import time

from .analyzer import explain
from .collector import Collector, Sampler
from .config import Config
from .platforms import get_probe
from .storage import Store


def main() -> None:
    parser = argparse.ArgumentParser(prog="whyslow", description="Find out why your laptop is slow.")
    parser.add_argument("command", choices=["collect", "snapshot", "status", "explain"])
    parser.add_argument("--at", help="time today to explain, like 14:41")
    args = parser.parse_args()
    config = Config()

    if args.command == "explain":
        at = None
        if args.at:
            hour, minute = (int(x) for x in args.at.split(":"))
            today = time.localtime()
            at = time.mktime(today[:3] + (hour, minute, 0) + today[6:])
        print(explain(Store(config.db_path), at=at).text())

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
