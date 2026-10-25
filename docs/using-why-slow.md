# Using why slow

This guide covers what you can do once why slow is installed. To install it, see the [README](../README.md).

## Recording

why slow can only explain what it recorded, so the collector needs to be running. `python -m whyslow install` starts it now and at every login, with no window. On Windows it adds a small script to your Startup folder. On Ubuntu it adds a systemd user service, which also restarts the collector if it ever stops. Neither needs admin rights.

To record only while a terminal is open, run `python -m whyslow collect` instead, and press Ctrl+C to stop. Only one collector runs at a time. If one is already running, a second one says so and exits.

The collector takes a snapshot every 5 seconds: how busy the CPU, memory and disk are, how long programs were kept waiting, the battery level, and the 5 busiest apps for CPU, memory and disk. It keeps them in memory and writes them to disk once a minute.

## The page

`python -m whyslow web` opens the page in your browser, at http://127.0.0.1:8765. It runs until you press Ctrl+C in the terminal. To use another port, add `--port 8766`.

At the top, the page shows how many slowdowns there were and, on a laptop, the battery level and whether it's charging. **Last 24 hours** switches the page between the last 3 and 24 hours.

### The timeline

Each bar is one minute, coloured by how slow it felt:

| Colour | Slowness score | Feels |
| --- | --- | --- |
| Green | under 40 | smooth |
| Amber | 40 to 70 | a bit slow |
| Red | 70 and up | slow |

The blue line is how much memory was in use, and the dashed green line is the battery level. A gap means nothing was recorded then, usually because the laptop was off or asleep.

Hover a bar to see that minute's slowness, CPU, memory and battery. A pulsing dot marks the most recent slow bar until you click one.

### Explanations

Click a bar, or **Explain the worst slowdown**, to get an explanation. It says:

- when the laptop was slow, and for how long
- what programs were waiting on: the CPU, memory, the disk, or a frozen window
- when the cause started building up, which is often a few minutes before it felt slow
- which app caused it, compared with how much it normally uses
- whether the laptop would have felt smooth without that app's extra use
- one thing to try

The dark panel on the right sums it up: how long it lasted, the peak score, what was waited on, the battery, and the app behind it.

**Explain the worst slowdown** looks at the last hour. If nothing was slow, it says so.

### Feedback

Under each explanation, **Was this right?** saves your 👍 or 👎 with the slowdown, its cause and the app it blamed. Nothing is sent anywhere. The votes are kept for tuning the explanations later.

## Commands

| Command | What it does |
| --- | --- |
| `python -m whyslow install` | Start recording now and at every login |
| `python -m whyslow uninstall` | Stop starting at login |
| `python -m whyslow collect` | Record in this terminal until Ctrl+C |
| `python -m whyslow web` | Open the page |
| `python -m whyslow explain` | Explain the worst slowdown in the last hour, in the terminal |
| `python -m whyslow explain --at 14:41` | Explain the slowdown around 2:41 pm today |
| `python -m whyslow status` | Show where the data is and how much is stored |
| `python -m whyslow snapshot` | Print one snapshot, to check that recording works |

Add `--demo` to `web` or `explain` to use a made-up day with three slowdowns instead of your own data. The demo data is kept separately and never mixes with yours.

## Where your data is kept

| System | Folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\whyslow\` |
| Ubuntu | `~/.local/share/whyslow/`, or `$XDG_DATA_HOME/whyslow/` if that's set |

The database is `whyslow.db` in that folder. Every snapshot is kept for 7 days. After that, it's summarised by the hour, and the hourly summaries are kept for 90 days. With the collector running all day, the database levels off at around 100 MB once it holds a full week.

## Stopping and removing why slow

1. Run `python -m whyslow uninstall`. On Ubuntu, this also stops the collector. On Windows, a collector that's already running keeps going until you log out, or you can end `pythonw.exe` in Task Manager.
2. Delete the data folder above.
3. Delete the `why-slow` folder you cloned.
