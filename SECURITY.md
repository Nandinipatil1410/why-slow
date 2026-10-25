# Security

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's [private vulnerability reporting](https://github.com/Nandinipatil1410/why-slow/security/advisories/new), not in a public issue. Say what an attacker could do, and how to reproduce it.

## How why slow is meant to be used

why slow runs on your own computer, for you alone:

- It never goes online, and sends nothing anywhere.
- The page listens only on `127.0.0.1`, so other computers can't reach it.
- It has no accounts or passwords. Any program running on the same computer can reach the page, like any other local server.
- It only reads system and app usage numbers. It never reads the contents of your files, and never changes anything outside its own data folder.
- What it records, like app names, usage and battery level, stays in its data folder until it's deleted after 7 days, or 90 days for hourly summaries.

Don't expose the page to a network, through a reverse proxy, a tunnel or port forwarding. Nothing in why slow is designed to stop other people from reading your data that way.
