# Developing why slow

## Setup

```bash
git clone https://github.com/Nandinipatil1410/why-slow.git
cd why-slow
python -m venv .venv
```

Activate it, with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on Ubuntu, then install it in editable mode with the test tools:

```bash
pip install -e ".[dev]"
```

## Running it

```bash
python -m whyslow web --demo   # the page, with a made-up day of data
python -m whyslow collect      # record in this terminal until Ctrl+C
python -m whyslow snapshot     # print one snapshot, to check the probes work
```

The demo, in `demo.py`, builds a day with three planted slowdowns: Chrome using too much memory, a Defender scan hammering the disk, and VS Code using the CPU. Its data is kept in a separate `demo` folder, so it never mixes with yours.

The page is a single file, `whyslow/static/index.html`, with no build step and no outside libraries. The server reads it on every request, so reload the browser to see a change.

## Tests

```bash
pytest
```

The tests use temporary databases and made-up snapshots, so they run on any system in a few seconds and never touch your real data.

## Project layout

```text
whyslow/
  __main__.py           the commands: install, collect, web, explain, status, snapshot
  config.py             every setting, each tied to a design decision
  models.py             what a snapshot contains
  collector.py          the 5 s loop, heartbeat probe, batching
  storage.py            SQLite tables, hourly summaries, cleanup, feedback
  analyzer/
    score.py            stage 1: a slowness score for each moment
    episodes.py         stage 2: the slow stretch, and when it started building
    attribution.py      stage 3: which app caused it, and the what-if
    story.py            stage 4: the plain-words explanation
  data/known_apps.json  friendly names and tips for background apps
  platforms/
    linux.py            Ubuntu: kernel pressure numbers (PSI), temperature
    windows.py          Windows: hard faults, "Not Responding" check
  web.py                local web server, 127.0.0.1 only
  static/index.html     the page
  demo.py               a made-up day with three slowdowns
  autostart.py          start at login: Windows Startup folder or systemd
tests/                  pytest tests for each part
docs/                   these guides
```

[How why slow works](how-it-works.md) explains each stage, and [DESIGN.md](DESIGN.md) the reasons behind them.

## Conventions

- Code that differs between Windows and Ubuntu goes in `platforms/`, nowhere else.
- Every setting goes in `config.py`, with a comment saying why it has that value.
- Explanations are written for people who don't know what a "page fault" is. Say what happened and what to do, with friendly numbers.
- Anything the collector does runs every 5 seconds, all day. Keep it cheap, and measure it.
