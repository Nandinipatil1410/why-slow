# whyslow

Tells you **why your laptop was slow**, in plain words, and what to do about it.

It quietly records how your laptop is doing every 5 seconds. Later you pick a slow
moment on a timeline and it explains what happened, for example:

> Your laptop was slow from 2:41 to 3:05 pm. Programs were stuck waiting for memory
> 38% of the time (normally 2%). Chrome grew to 3.1 GB, 1.9 GB above its usual...
> **Try:** close the Chrome tabs you're not using.

Runs on Windows and Ubuntu, fully offline. Nothing leaves your laptop, and there's no AI model inside.

## Status

| Part | State |
| --- | --- |
| Collector (snapshots every 5 s) | done |
| Storage (SQLite, 7 days detail + 90 days hourly) | done |
| Analyzer (explains a slow moment) | done (`python -m whyslow explain`) |
| Web page (timeline) | next |

## Try it

```bash
python -m venv .venv
# Ubuntu: source .venv/bin/activate     Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python -m whyslow snapshot   # print one snapshot, to check it works
python -m whyslow collect    # record until Ctrl+C
python -m whyslow status     # how much is stored
pytest                       # run the tests
```

Data is stored in `~/.local/share/whyslow/` on Ubuntu and `%LOCALAPPDATA%\whyslow\` on Windows.

## How it's built

```
whyslow/
  config.py           every setting, each tied to a design decision
  models.py           what a snapshot contains
  collector.py        the 5 s loop, heartbeat probe, batching
  storage.py          SQLite tables, hourly summaries, cleanup
  analyzer/           score -> slow stretch -> who caused it -> story
  data/known_apps.json  friendly names + tips for background apps
  platforms/
    linux.py          Ubuntu: kernel pressure numbers (PSI), temperature
    windows.py        Windows: hard faults, "Not Responding" check
```

The design and the reasons behind each choice are in [docs/DESIGN.md](docs/DESIGN.md).
