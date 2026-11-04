"""Configuration.

Three places, kept apart so the package can be redistributed:
  package   coach/defaults/...            generic default prompts (shipped, no personal data)
  instance  /etc/coach-agent/             config.yaml, .env, athlete profile, prompt overrides
  state     /var/lib/coach-agent/         database, OAuth tokens (service user's home)

Relative paths in config.yaml resolve against the instance directory first, then the
packaged defaults, so an instance only carries the files it actually customises.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

DEFAULTS_DIR = Path(str(files("coach") / "defaults"))
SYSTEM_CONFIG = Path("/etc/coach-agent/config.yaml")

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def _expand(value: Any) -> Any:
    """Recursively replace ${VAR} / ${VAR:-default} in strings."""
    if isinstance(value, str):
        def sub(m: re.Match) -> str:
            var, default = m.group(1), m.group(2)
            if var in os.environ:
                return os.environ[var]
            if default is not None:
                return default
            raise KeyError(f"Environment variable {var} is not set (referenced in config)")
        return _ENV_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def default_config_path() -> Path:
    """$COACH_CONFIG, else ./config.yaml (development), else /etc/coach-agent/config.yaml."""
    if os.environ.get("COACH_CONFIG"):
        return Path(os.environ["COACH_CONFIG"])
    local = Path("config.yaml")
    return local if local.exists() else SYSTEM_CONFIG


@dataclass
class JobConfig:
    name: str
    cron: str
    prompt_file: str
    enabled: bool = True
    model: str | None = None
    # If the agent's reply is exactly this token, nothing is sent.
    silent_token: str | None = None
    # If the agent's reply starts with this token, the job retries later.
    retry_token: str | None = None
    retry_minutes: int = 45
    max_retries: int = 0
    # If set, each delivered reply is also appended to the shared journal under this topic.
    journal_topic: str | None = None


# Intervals.icu Connector tools whose successful calls are logged to the journal.
DEFAULT_JOURNAL_LOG_TOOLS = [
    "schedule_workout", "update_planned_workout", "delete_planned_event", "apply_calendar_changes",
    "schedule_calendar_event", "update_calendar_event", "log_wellness", "update_activity",
    "update_sport_settings",
]


@dataclass
class JournalConfig:
    spreadsheet_id: str
    credentials_file: Path
    sheet: str = "Journal"
    channel: str = "Telegram"
    context_days: int = 14
    context_max_rows: int = 40
    log_tools: list[str] = field(default_factory=lambda: list(DEFAULT_JOURNAL_LOG_TOOLS))


@dataclass
class Config:
    base_dir: Path                 # the instance directory (where config.yaml lives)
    timezone: ZoneInfo
    athlete_name: str
    language: str
    telegram_token: str
    allowed_chat_ids: list[int]
    default_chat_id: int
    tg_ipv4_only: bool
    tg_connect_timeout: float
    tg_read_timeout: float
    tg_proxy: str | None
    model: str
    max_turns: int
    max_budget_usd: float | None
    session_max_age_hours: float
    setting_sources: list[str]
    system_prompt_file: str
    context_files: list[str]
    mcp_servers: dict[str, dict]
    allowed_tools: list[str]
    disallowed_tools: list[str]
    db_path: Path
    workdir: Path
    jobs: list[JobConfig] = field(default_factory=list)
    journal: JournalConfig | None = None

    def resolve(self, p: str | Path) -> Path:
        """Instance file if present, else the packaged default (which may not exist either)."""
        p = Path(p)
        if p.is_absolute():
            return p
        local = self.base_dir / p
        return local if local.exists() else DEFAULTS_DIR / p

    # Kept for callers that expect it.
    path = resolve


# Claude Code built-ins we never want a chat bot to have unless deliberately enabled.
DEFAULT_DISALLOWED = [
    "Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite",
]


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or default_config_path()).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No config at {path}. Copy examples/config.example.yaml there.")
    base = path.parent
    load_dotenv(base / ".env")
    raw = _expand(yaml.safe_load(path.read_text()))

    tg = raw.get("telegram", {})
    agent = raw.get("agent", {})
    athlete = raw.get("athlete", {})
    allowed = [int(x) for x in tg.get("allowed_chat_ids", [])]
    if not allowed:
        raise ValueError("telegram.allowed_chat_ids must list at least one chat id")

    jobs = [JobConfig(name=name, **spec) for name, spec in (raw.get("jobs") or {}).items()]

    journal = None
    jr = raw.get("journal") or {}
    if jr.get("enabled", False):
        cred = Path(jr["credentials_file"])
        journal = JournalConfig(
            spreadsheet_id=jr["spreadsheet_id"],
            credentials_file=cred if cred.is_absolute() else base / cred,
            sheet=jr.get("sheet", "Journal"),
            channel=jr.get("channel", "Telegram"),
            context_days=int(jr.get("context_days", 14)),
            context_max_rows=int(jr.get("context_max_rows", 40)),
            log_tools=list(jr.get("log_tools", DEFAULT_JOURNAL_LOG_TOOLS)),
        )

    data_dir = Path(raw.get("data_dir", "data"))
    data_dir = data_dir if data_dir.is_absolute() else base / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        base_dir=base,
        timezone=ZoneInfo(raw.get("timezone", "UTC")),
        athlete_name=athlete.get("name", "the athlete"),
        language=athlete.get("language", "English"),
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        allowed_chat_ids=allowed,
        default_chat_id=int(tg.get("default_chat_id", allowed[0])),
        tg_ipv4_only=bool(tg.get("ipv4_only", False)),
        tg_connect_timeout=float(tg.get("connect_timeout", 15)),
        tg_read_timeout=float(tg.get("read_timeout", 30)),
        tg_proxy=tg.get("proxy") or None,
        model=agent.get("model", "claude-sonnet-5-5"),
        max_turns=int(agent.get("max_turns", 20)),
        max_budget_usd=agent.get("max_budget_usd"),
        session_max_age_hours=float(agent.get("session_max_age_hours", 16)),
        setting_sources=list(agent.get("setting_sources", [])),
        system_prompt_file=agent.get("system_prompt_file", "prompts/system.md"),
        context_files=list(agent.get("context_files", [])),
        mcp_servers=raw.get("mcp_servers") or {},
        allowed_tools=raw.get("allowed_tools") or [],
        disallowed_tools=raw.get("disallowed_tools", DEFAULT_DISALLOWED),
        db_path=data_dir / "coach.db",
        workdir=data_dir / "work",
        jobs=jobs,
        journal=journal,
    )
