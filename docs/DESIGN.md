# Design

Full write-ups: [v1 design](https://claude.ai/artifact/9jfjnoe4xP2EqRauqcSWRW) and
[analyzer research](https://claude.ai/artifact/1rr5AXtfvSR1ZkDJWUN2yo).

**Ground rule:** the tool must never cause the slowness it explains.

| Decision | Choice | Why | Gave up |
| --- | --- | --- | --- |
| Scope | Timeline + explain a slow moment | Smallest version that needs data over time | Pop-ups, weekly trends (later) |
| Snapshot rate | Every 5 s; top 5 apps by CPU, RAM and disk | Catches freezes you notice; measured ~8 ms CPU per snapshot | Blips under 5 s |
| Storage | SQLite; 7 days full, hourly for 90 days; write once a minute | Small, no server, little disk activity | Old second-by-second detail |
| Analyzer | Stats pipeline, no LLM | Offline, no extra RAM, every claim traceable to a number | Free-form AI wording |
| Platforms | Windows + Ubuntu, OS code only in `platforms/` | Covers both; one codebase | Windows temperatures in v1 |

## Measuring "slow": waiting, not usage

100% CPU isn't slow if nothing is waiting. So besides usage we record how long programs waited:

| Signal | Ubuntu | Windows |
| --- | --- | --- |
| CPU waiting | PSI cpu | heartbeat probe |
| Memory waiting | PSI memory | hard faults/s |
| Disk waiting | PSI io + disk latency | disk latency |
| Frozen window | - | "Not Responding" check |
| Heartbeat probe | yes | yes |

## Analyzer pipeline

1. Measure waiting (above)
2. Find when the slowdown started (change-point detection)
3. Find which app caused how much (explanatory power x surprise, plus a what-if)
4. Write the story from templates, ending with one action

Later: system events (v1.1), repeat detection (needs ~2 weeks of data), a small model trained on 👍/👎 feedback.
