# Contributing

Issues and pull requests are welcome.

## Setting up

```bash
git clone https://github.com/hdbonnett/intervals-coach-agent.git
cd intervals-coach-agent
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

The test suite needs no network access or API keys. To try the bot against real services, follow
the foreground instructions in [docs/INSTALL.md](docs/INSTALL.md#7-running-in-the-foreground-any-platform),
using the git-ignored `instance/` directory for your config and secrets.

## Guidelines

- **Keep personal data out of the repository.** Names, chat ids, sheet ids, keys and athlete
  details belong in an instance directory, never in code, defaults or examples.
  `test_repository_has_no_personal_data` checks for known personal terms.
- **Guarantees in code, judgement in prompts.** Anything that must always hold (who can talk to
  the agent, which tools exist, spend limits, approval for writes) belongs in code or config, not
  only in a prompt. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **New capabilities**: say in the pull request what data they read, what they can change, and
  whether they add a new way for data to leave. Off by default is the norm for anything that writes.
- **Tests**: add or update tests for behaviour you change. The agent wrapper can be tested
  against a fake SDK stream; see `tests/test_core.py`.
- **Changelog**: add a line under an "Unreleased" heading in [CHANGELOG.md](CHANGELOG.md).

By contributing, you agree that your contributions are licensed under the [MIT licence](LICENSE).
