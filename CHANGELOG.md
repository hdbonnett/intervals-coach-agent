# Changelog

All notable changes to this project are recorded here. The project uses
[semantic versioning](https://semver.org/); while it is 0.x, minor versions may change
configuration.

## [0.3.0] - 2026-11-05

First public release.

### Added
- Shared journal: an optional Google Sheet that bridges Telegram and claude.ai conversations.
  Delivered job output (`journal_topic`) and every successful Intervals.icu write are logged by
  code; the `journal_add` tool logs decisions from chat; recent rows are loaded into every
  conversation.
- `install.sh` for any Linux distribution with systemd (dnf/yum, apt, zypper, pacman). It is safe
  to re-run, never overwrites instance or state files, and ends with a checklist.
- Install guide for Linux, macOS, Windows (WSL2) and foreground use (`docs/INSTALL.md`).
- Architecture guide (`docs/ARCHITECTURE.md`) with editable diagrams.

### Changed
- The distribution is now named `intervals-coach-agent`. The import package (`coach`) and the
  command (`coach-agent`) are unchanged.
- The example config defaults to `timezone: UTC` and chat id `0` (not set).
- `coach-as` uses `runuser` when available, so `sudo` is no longer required.

## [0.2.1] - 2026-11-02

### Added
- Telegram `ipv4_only`, `connect_timeout`, `read_timeout` and `proxy` options.
- Indefinite retry of the initial Telegram connection.

## [0.2.0] - 2026-11-02

### Changed
- Split into package, instance (`/etc/coach-agent`) and state (`/var/lib/coach-agent`), with
  instance-first prompt resolution, so the code carries no personal data.
- Uses the official Intervals.icu Connector (`https://mcp.intervals.icu/mcp`) with OAuth.

## [0.1.0] - 2026-11-02

### Added
- Telegram chat with the Claude Agent SDK and an Intervals.icu MCP server.
- Morning brief with retry until wellness data has synced; evening upcoming-events scan.
- Reminders and notes as in-process tools; SQLite store; cost log; systemd unit.
