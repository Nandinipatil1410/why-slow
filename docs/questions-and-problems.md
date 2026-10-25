# Questions and problems

Answers to common problems with recording, the page, and the explanations. For how to use why slow, see [Using why slow](using-why-slow.md).

## The page says "No data yet. Is the collector running?"

Nothing has been recorded in the time shown. Check, in order:

- **Is a collector running?** Run `python -m whyslow status`. If the snapshot count doesn't go up when you run it again a minute later, nothing is recording. Run `python -m whyslow install`, or `python -m whyslow collect` to record in a terminal.
- **Has it written yet?** Snapshots are written once a minute, so a new collector shows nothing for the first minute.
- **Is it the same Python?** The collector and the page must use the same data folder. If you installed with one Python and run the page with another, run both from the same `.venv`.

## It says "A collector is already running"

Only one collector runs at a time, so nothing is recorded twice. This is normal after `install`, which starts one in the background. If you're sure none is running, delete `collector.pid` from the [data folder](using-why-slow.md#where-your-data-is-kept).

## The port is in use

The page uses port 8765. If another program has it, starting the page fails. Use another port:

```bash
python -m whyslow web --port 8766
```

## "No slowdown found"

Nothing scored as slow around that moment, or in the last hour for **Explain the worst slowdown**. Click a red or amber bar instead. If your laptop felt slow but the timeline is green, the slowness may have been something why slow can't see yet, like a slow website or a slow network. Click 👎 on a wrong explanation, so it can be tuned.

## The explanation blames the wrong app

For its first 12 hours, why slow doesn't know what's normal for each app, so it compares with the few minutes before the slowdown, which is less reliable. Explanations get better after a day of recording. Click 👎 when it's wrong.

## There's no battery chip or battery line

The battery is only shown on a laptop, and only for times recorded since battery recording was added. Desktops, and some laptops whose battery Windows or Ubuntu doesn't report, show none.

## The timeline has gaps

A gap means nothing was recorded, usually because the laptop was off, asleep or hibernating, or the collector wasn't running. After a restart, the collector starts again at login if you used `install`.

## Starting at login doesn't work

- **On Windows,** check that `whyslow.vbs` is in your Startup folder: press Win+R, type `shell:startup`, and press Enter. Run `python -m whyslow install` again from the `.venv` you use, since the script points at that Python.
- **On Ubuntu,** run `systemctl --user status whyslow`. If it failed, `journalctl --user -u whyslow` shows why.

## Does it slow my laptop down?

It's built not to. A snapshot takes about 8 ms of CPU every 5 seconds, it writes to disk once a minute, and on Ubuntu it runs at a lower priority than your apps. The page only does work when you open it.

## Does it send anything anywhere?

No. why slow never goes online. Your data stays in the [data folder](using-why-slow.md#where-your-data-is-kept), and the page is only reachable from your own computer.
