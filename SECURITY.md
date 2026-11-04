# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. Include what you found, how to
reproduce it, and the version (`pip show intervals-coach-agent`).

You can expect an acknowledgement within a week. Fixes are released as patch versions and noted
in [CHANGELOG.md](CHANGELOG.md).

## Scope

In scope:
- the agent code, the installer and the systemd unit;
- ways for someone other than the allow-listed owner to reach the agent;
- ways for text in Intervals.icu data, journal entries or tool results to make the agent take
  actions the owner did not ask for, or send data anywhere other than the owner's chat and the
  configured services (prompt injection that leads to a consequential action or data leaving);
- weaknesses in how secrets and OAuth tokens are stored.

Out of scope: vulnerabilities in Intervals.icu, Telegram, the Claude API or the Claude Agent SDK
themselves. Please report those to the respective vendor.

## Hardening notes for operators

- Keep `allowed_tools` minimal. Each write tool you enable lets text the model reads have
  consequences outside the conversation.
- Don't add tools that can send data to arbitrary destinations (web fetch, email, links).
  Together with private data and untrusted content, they complete the "lethal trifecta"; see
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#7-trust-boundaries-and-security).
- Treat backups of `/etc/coach-agent` and `/var/lib/coach-agent` as secret.
