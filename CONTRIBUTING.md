# Contributing

Bug reports, ideas and pull requests are welcome. For anything larger than a small fix, open an issue first, so we can agree on an approach before you spend time on it.

A wrong explanation is a useful bug report. Say what the page said, what you think really happened, and whether you're on Windows or Ubuntu.

## Setup and tests

[Developing why slow](docs/development.md) covers setting up, the demo data, the project layout and running the tests.

## Sending a change

- Keep each pull request to one change, with tests for new behaviour.
- Keep OS-specific code in `whyslow/platforms/`.
- To add a friendly name or tip for an app, add a line to `whyslow/data/known_apps.json`.
- Update the docs when behaviour changes.
- Follow the style of the code around your change.
