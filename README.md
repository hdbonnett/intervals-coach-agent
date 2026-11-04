# intervals-coach-agent

A personal training assistant you talk to on Telegram. It reads your
[Intervals.icu](https://intervals.icu) data through the official Intervals.icu Connector, sends a
morning readiness brief based on your sleep, HRV and training load, reminds you about upcoming
tests and races, and answers questions about your training. It is built on the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview), so new jobs, tools and data
sources are added through configuration rather than code.

> **Status: early (0.x).** It runs daily for its author. Interfaces and configuration may still
> change between minor versions; see [CHANGELOG.md](CHANGELOG.md).

## What it does

| | |
|---|---|
| **Chat** | Ask anything about your training. Answers use your real Intervals.icu numbers; conversations continue until `/new` or 16 hours idle. |
| **Morning brief** | Daily at a time you choose. Sleep, HRV, resting HR, how you've logged feeling, load and form, and today's plan become a 🟢 / 🟡 / 🔴 call with a concrete adjustment. If last night's sleep hasn't synced yet, it waits and retries. |
| **Upcoming scan** | Each evening it finds tests, races and long sessions in the next 14 days and schedules preparation reminders. It stays silent if nothing is new. |
| **Reminders and notes** | "Remind me Thursday at 7 pm to pump the tyres." Lasting facts you mention ("away 10–14 Dec") are remembered for later conversations. |
| **Calendar changes** (opt-in) | With write tools enabled, it can move or add workouts after you confirm. |
| **Shared journal** (optional) | A Google Sheet that also connects your claude.ai conversations, so decisions made in either place are known in both. |
| **Commands** | `/brief /plan /reminders /notes /jobs /new /cost /help`, and `/whoami` for setup |

## How it works

```
 Telegram ──long-poll──▶ gateway ──▶ orchestrator ──▶ agent runtime (Claude Agent SDK) ──▶ Claude API
                                         ▲    │              │  ├─▶ MCP: Intervals.icu Connector (OAuth)
            reminder dispatch (no model) ┤    │              │  └─▶ MCP: coach tools (reminders, notes, journal)
            scheduler: cron jobs ────────┘    ▼              ▼
                                       SQLite: sessions · reminders · notes · runs    Google Sheet (optional)
```

One Python process, no listening ports. Deterministic code handles everything except judgement:
who may talk to the bot, which tools exist, budgets, retries, scheduling and delivery. The model
decides what to look up and what to advise. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
explains the design: components, data flows, state, trust boundaries and how to extend an agent
like this safely.

## Requirements

- An **Intervals.icu** account with access to the Connector (during its beta, Supporters only).
- A **Telegram** bot token from @BotFather.
- An **Anthropic API key** from the Claude Console. This is API billing, separate from claude.ai plans.
- Python **3.11+** on an always-on machine: Linux with systemd (installer provided), macOS, or
  Windows via WSL2. About 400 MB of disk and 2 GB RAM.

## Quick start (Linux with systemd)

```bash
git clone https://github.com/hdbonnett/intervals-coach-agent.git
cd intervals-coach-agent
sudo ./install.sh
```

The installer builds a sandboxed service and ends with a checklist: add your keys to
`/etc/coach-agent/.env`, sign in to Intervals.icu, and set your Telegram chat id. Re-run it after
each item; it starts the service once nothing is left. Full instructions for every platform are
in [docs/INSTALL.md](docs/INSTALL.md).

## Configuration at a glance

Your settings live outside the code, so upgrades never touch them:

| Location (Linux) | Contents |
|---|---|
| `/opt/coach-agent/` | The package (rebuilt by each install) |
| `/etc/coach-agent/config.yaml` | Timezone, schedules, models, allowed tools, optional journal |
| `/etc/coach-agent/.env` | Secrets: API key, bot token |
| `/etc/coach-agent/athlete/profile.md` | Your goals, events and constraints, loaded into every conversation |
| `/etc/coach-agent/prompts/` | Optional overrides of the [default prompts](coach/defaults/prompts/) |
| `/var/lib/coach-agent/` | State: database and the Intervals.icu sign-in |

Start from [examples/config.example.yaml](examples/config.example.yaml) and
[examples/athlete-profile.example.md](examples/athlete-profile.example.md).

## Extending

- **A scheduled job:** add a prompt file and a block under `jobs:` (cron, model, retry and silence options).
- **Another data source** (weather, calendar, gym log): add an MCP server under `mcp_servers:` and
  list the tools you allow in `allowed_tools`.
- **A built-in tool:** add a module to `coach/tools/` with a `build(ctx)` function.
- **A command or input type** (voice notes, photos): one handler in `coach/telegram_io.py`.

Before adding a capability that can send data anywhere new, read
[Evolving an agent safely](docs/ARCHITECTURE.md#10-evolving-an-agent-safely).

## Security

- Only allow-listed Telegram chats reach the agent; there are no inbound ports.
- Tools are deny-by-default. Only those in `allowed_tools` run. The shell, file and web tools
  built into Claude Code are disallowed, and host Claude settings are ignored.
- Text from Intervals.icu (activity names, notes, calendar entries) is treated as data, never
  as instructions. Calendar writes are off by default.
- Each request has a spend cap, and runs and costs are logged (`/cost`).
- On Linux the service runs as an unprivileged user in a systemd sandbox, with only its state
  directory writable.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

The tests need no network or API key. They cover configuration, storage, tools, formatting,
scheduling prompts, the journal (against a mock Sheets API), and the agent wrapper (against a
fake SDK stream). One test fails if personal data appears in any shipped file. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Disclaimer

This is an independent project, not affiliated with or endorsed by Intervals.icu, Anthropic or
Telegram. Its advice comes from a language model reading your data. It is not medical advice;
use your own judgement and see a professional about health concerns.

## Licence

[MIT](LICENSE)
