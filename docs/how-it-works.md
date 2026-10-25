# How why slow works

why slow has two parts: a collector that records how the laptop is doing, and a local web server that turns those records into a timeline and explanations. Both are plain Python, with `psutil` as the only required library, plus `pywin32` on Windows. There's no AI model: every sentence comes from a measured number and a template.

```text
every 5 s: collector -> snapshot (usage, waiting, top apps, battery)
once a minute: -> SQLite
on a click: score each moment -> find the slow stretch -> find the app -> write the story
```

The ground rule is that the tool must never cause the slowness it explains. A snapshot costs about 8 ms of CPU, snapshots are written in one batch a minute, and on Ubuntu the collector runs at a lower priority than your apps.

The reasons behind each choice are in [DESIGN.md](DESIGN.md).

## Snapshots

Every 5 seconds, `collector.py` records:

- **Usage:** CPU %, memory % and MB free, swap, disk reads and writes, how full the system drive is, and the CPU clock speed, which drops when a laptop overheats or saves power.
- **Waiting:** how long programs were kept waiting. See below.
- **Apps:** the 5 busiest apps by CPU, by memory and by disk activity, usually about 10 apps in all. Processes with the same name are added together, so Chrome's 30 processes count as one `chrome`.
- **Battery:** the level, and whether the charger is plugged in. Desktops have none.

## Measuring "slow": waiting, not usage

100% CPU isn't slow if nothing is waiting for it. So besides usage, why slow records how long programs waited. Each operating system offers different numbers, and all the OS-specific code is in `whyslow/platforms/`.

| What was waited on | Ubuntu | Windows |
| --- | --- | --- |
| CPU | kernel pressure (PSI) | heartbeat probe |
| Memory | kernel pressure (PSI) | hard page faults per second, once memory is 80% full |
| Disk | kernel pressure (PSI), disk latency | disk latency |
| A frozen window | - | Windows' "Not Responding" check on the window in front |

The **heartbeat probe** works on both: the collector asks to wake every 5 seconds, and notes how late it actually woke. When the CPU is swamped, even this tiny task runs late. A lag of more than two intervals means the laptop was asleep, and isn't counted.

## Stage 1: a score for each moment

`analyzer/score.py` turns each waiting signal into a 0 to 1 "badness" between two limits, like 10 ms (fine) and 60 ms (bad) for disk latency. The moment's slowness score is the worst signal times 100, and the page colours it: under 40 is smooth, 70 and up is slow. A frozen window always scores 100.

The limits started as common rules of thumb, and were tuned on a real laptop. For example, Windows' hard page faults reached 3,000 per second with nothing slow, because apps also read files that way, so that signal only counts once memory is nearly full.

## Stage 2: the slow stretch

`analyzer/episodes.py` finds the stretch of slow moments around the one you clicked. A stretch starts when the score goes above 40, and only ends when it drops below 20, so a score hovering around 30 doesn't split into many tiny stretches. Stretches less than a minute apart are joined, and a single slow snapshot on its own is ignored as a blip.

Slowness often comes after its cause: memory fills for a few minutes before things freeze. So it also looks back before the stretch for the moment a usage number shifted the most. That's the "started building up at" time.

## Stage 3: which app caused it

`analyzer/attribution.py` scores each app on two things, an approach borrowed from Microsoft's Adtributor:

- **Explanatory power:** what share of the total rise this app accounts for. "Chrome added 1.8 GB of the 2.2 GB rise" is 82%.
- **Surprise:** how unusual this is for this app, against its own normal, from its past hourly averages. An app that's always big isn't the story.

The app with the best mix of both is the culprit. With less than 12 hours of history, "normal" is the few minutes before the stretch instead.

Then a **what-if**: take away the culprit's extra use and recompute. If memory would have dropped from 81% to 57%, the culprit really was the cause. If not, the laptop is simply short of memory or CPU for this workload, and the story says that instead.

Per-app disk numbers on Windows include reads served from memory, so an app is only blamed for a disk slowdown when the disk itself was busy.

## Stage 4: the story

`analyzer/story.py` puts the facts in a fixed order, what, when, who, why and what to try, and fills sentence templates with friendly numbers, like "3.0 GB" and "2:06 pm".

`whyslow/data/known_apps.json` gives background apps that people don't recognise a friendly name and a specific tip. `MsMpEng.exe` becomes "Windows Defender (antivirus)", with how to reschedule its scans. To add one, add a line there.

## Storage

`storage.py` keeps everything in one SQLite file, in WAL mode, so the page can read while the collector writes:

- `snapshots` and `app_usage`: every snapshot, for 7 days.
- `hourly_system` and `hourly_apps`: hourly averages and peaks, for 90 days. They're also each app's "normal" in stage 3.
- `feedback`: your 👍 and 👎.

Once an hour, the collector summarises the last hour and deletes rows that are too old. When a newer version adds a column, like the battery, it's added to the existing database, so updating never loses your history.

## The page

`web.py` uses Python's built-in HTTP server, listening only on `127.0.0.1`. It serves `static/index.html`, a single page with no outside libraries, and a small JSON API:

| Request | Returns |
| --- | --- |
| `GET /api/timeline?hours=24` | One point per minute: worst score, average CPU and memory, battery |
| `GET /api/explain?at=<unix time>` | The explanation for that moment, or the worst in the last hour without `at` |
| `POST /api/feedback` | Saves a 👍 or 👎 |
| `GET /api/info` | Whether this is demo data |
