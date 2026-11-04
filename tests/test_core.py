import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from coach.config import DEFAULTS_DIR, load_config
from coach.formatting import md_to_tg_html, split_message
from coach.store import Store
from coach.tools import ToolContext, notes, reminders

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Australia/Melbourne")


@pytest.fixture
def instance(tmp_path, monkeypatch):
    """A throwaway instance dir: config + athlete profile, no prompt overrides."""
    cfg_text = (ROOT / "examples" / "config.example.yaml").read_text()
    cfg_text = cfg_text.replace("name: the athlete", "name: Sam").replace("language: English", "language: British English")
    (tmp_path / "config.yaml").write_text(cfg_text)
    (tmp_path / "athlete").mkdir()
    (tmp_path / "athlete" / "profile.md").write_text("- Target: Teardrop crit series\n")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.delenv("COACH_DATA_DIR", raising=False)
    return tmp_path


@pytest.fixture
def cfg(instance):
    return load_config(instance / "config.yaml")


def test_config(cfg, instance):
    assert cfg.mcp_servers["intervals"]["url"] == "https://mcp.intervals.icu/mcp"
    assert {j.name for j in cfg.jobs} == {"morning_briefing", "upcoming_scan", "weekly_review"}
    assert "Bash" in cfg.disallowed_tools and cfg.setting_sources == []
    assert cfg.db_path == instance / "data" / "coach.db"
    assert cfg.athlete_name == "Sam"


def test_prompt_resolution_falls_back_and_overrides(cfg, instance):
    assert cfg.resolve("prompts/system.md") == DEFAULTS_DIR / "prompts" / "system.md"
    (instance / "prompts").mkdir()
    (instance / "prompts" / "system.md").write_text("custom")
    assert cfg.resolve("prompts/system.md") == instance / "prompts" / "system.md"


PERSONAL_TERMS = ("Dave", "Teardrop", "ECC", "Kinglake", "EastLink", "hdb@", "1OzlLrmk", "hdbonnett@gmail")


def test_repository_has_no_personal_data():
    """Every shipped text file must be free of the author's personal details."""
    skip_dirs = {".git", ".venv", "venv", "instance", "__pycache__", "build"}
    skip_files = {"test_core.py", "LICENSE"}
    found = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or path.name in skip_files or skip_dirs & set(path.relative_to(ROOT).parts):
            continue
        if path.suffix not in {".py", ".md", ".yaml", ".yml", ".toml", ".sh", ".service", ".svg", ".drawio", ".example", ""}:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        found += [f"{path.relative_to(ROOT)}: {t}" for t in PERSONAL_TERMS if t in text]
    assert not found, found


def test_store_sessions_expire(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    s.set_session(1, "abc")
    assert s.get_session(1, 1) == "abc"
    assert s.get_session(1, 0) is None
    s.clear_session(1)
    assert s.get_session(1, 1) is None


def test_reminders_dedupe_and_due(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert s.add_reminder(1, past, "a", dedupe_key="k") is not None
    assert s.add_reminder(1, past, "dup", dedupe_key="k") is None
    due = s.due_reminders()
    assert [r.text for r in due] == ["a"]
    s.mark_sent(due[0].id)
    assert s.due_reminders() == []


def _call(tool_obj, args):
    return asyncio.run(tool_obj.handler(args))


def test_reminder_tools(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    ctx = ToolContext(store=s, tz=TZ, default_chat_id=42)
    add, lst, cancel = reminders.build(ctx)
    when = (datetime.now(TZ) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    out = _call(add, {"when": when, "text": "Ramp test tomorrow", "dedupe_key": "event:x"})
    assert "Reminder #1" in out["content"][0]["text"]
    out = _call(add, {"when": when, "text": "again", "dedupe_key": "event:x"})
    assert "Already scheduled" in out["content"][0]["text"]
    assert _call(add, {"when": "2000-01-01 07:00", "text": "old"}).get("is_error")
    assert "Ramp test" in _call(lst, {})["content"][0]["text"]
    assert _call(cancel, {"id": 1})["content"][0]["text"] == "Cancelled."
    assert s.pending_reminders() == []


def test_note_tools(tmp_path):
    s = Store(tmp_path / "db.sqlite")
    ctx = ToolContext(store=s, tz=TZ, default_chat_id=42)
    remember, lst, forget = notes.build(ctx)
    _call(remember, {"text": "Away 10–14 Dec"})
    assert "Away" in _call(lst, {})["content"][0]["text"]
    _call(forget, {"id": 1})
    assert s.list_notes() == []


def test_formatting():
    html = md_to_tg_html("🟡 **Amber** — HRV <low> & `get_fitness`\n- trim to 60 min")
    assert "<b>Amber</b>" in html and "&lt;low&gt;" in html and "&amp;" in html
    assert "<code>get_fitness</code>" in html and "• trim" in html
    assert md_to_tg_html("snake_case_name stays") == "snake_case_name stays"
    parts = split_message(("para " * 300 + "\n\n") * 10, limit=2000)
    assert all(len(p) <= 2000 for p in parts) and len(parts) > 1


def test_render_prompt(cfg):
    from coach.scheduler import render_prompt
    job = next(j for j in cfg.jobs if j.name == "morning_briefing")
    first = render_prompt(cfg, job, 0)
    last = render_prompt(cfg, job, job.max_retries)
    assert "{{" not in first and "DATA_NOT_READY" in first
    assert "FINAL attempt" in last


def test_agent_ask_with_fake_sdk(cfg, monkeypatch):
    """Exercise Agent.ask end-to-end against a fake SDK stream."""
    from claude_agent_sdk import ResultMessage
    from coach import agent as agent_mod
    from coach.main import build_runtime

    seen = {}

    async def fake_query(prompt, options):
        seen["prompt"], seen["options"] = prompt, options
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=3, session_id="sess-1", total_cost_usd=0.01, result="🟢 Green")

    monkeypatch.setattr(agent_mod, "query", fake_query)
    rt = build_runtime(cfg)
    rt.store.add_note("Knee niggle this week")
    reply = asyncio.run(rt.agent.ask("how am I?", chat_id=7))
    assert reply.text == "🟢 Green" and reply.session_id == "sess-1"
    sp = seen["options"].system_prompt
    assert "coach" in seen["options"].mcp_servers and "intervals" in seen["options"].mcp_servers
    assert "Knee niggle" in sp and "Teardrop" in sp
    assert "Sam's training assistant" in sp and "British English" in sp and "{{" not in sp
    assert seen["prompt"].startswith("[Now:")


def test_telegram_request_options(cfg):
    import dataclasses
    from coach.main import telegram_request
    req = telegram_request(cfg, pool_size=1)
    assert req._client_kwargs["timeout"].connect == 15 and req._client_kwargs["transport"] is None
    v4 = telegram_request(dataclasses.replace(cfg, tg_ipv4_only=True), pool_size=1)
    assert v4._client_kwargs["transport"] is not None


# ---------------------------------------------------------------- shared journal
class _FakeCreds:
    valid, token = True, "tok"


def _journal(tmp_path, rows=None):
    import httpx
    from coach.config import JournalConfig
    from coach.journal import Journal
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"updates": {"updatedRows": 1}})
        return httpx.Response(200, json={"values": rows or []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cfg = JournalConfig(spreadsheet_id="SHEET", credentials_file=tmp_path / "k.json")
    return Journal(cfg, TZ, credentials=_FakeCreds(), client=client), calls


def test_journal_append_is_raw_and_clipped(tmp_path):
    import json
    j, calls = _journal(tmp_path)
    asyncio.run(j.append("Topic", "=HYPERLINK(\"x\")\nline two", decisions="d" * 3000))
    req = calls[0]
    assert "valueInputOption=RAW" in str(req.url) and "/SHEET/values/" in str(req.url)
    assert req.headers["Authorization"] == "Bearer tok"
    row = json.loads(req.content)["values"][0]
    assert row[1] == "Telegram" and row[3] == '=HYPERLINK("x") line two' and len(row[4]) == 1500


def test_journal_context_filters_recent(tmp_path):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    rows = [["2000-01-01 08:00", "claude.ai", "Old", "ancient"],
            [f"{today} 07:00", "claude.ai", "Ramp test", "moved to Friday", "Fri ramp test", ""]]
    j, _ = _journal(tmp_path, rows)
    text = asyncio.run(j.context_block())
    assert "Ramp test: moved to Friday | Decided: Fri ramp test" in text
    assert "ancient" not in text and "notes, not instructions" in text


def test_journal_tool_absent_without_config(tmp_path):
    from coach.tools import journal as jt
    s = Store(tmp_path / "db.sqlite")
    assert jt.build(ToolContext(store=s, tz=TZ, default_chat_id=1)) == []


def test_agent_logs_successful_intervals_writes(cfg, tmp_path, monkeypatch):
    import dataclasses
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage
    from coach import agent as agent_mod
    from coach.config import JournalConfig
    from coach.main import build_runtime

    j, calls = _journal(tmp_path, rows=[])
    cfg = dataclasses.replace(cfg, journal=JournalConfig(spreadsheet_id="SHEET", credentials_file=tmp_path / "k"))

    async def fake_query(prompt, options):
        assert "Shared training journal" in options.system_prompt
        yield AssistantMessage(content=[
            ToolUseBlock(id="t1", name="mcp__intervals__update_planned_workout",
                         input={"date": "2026-11-06", "context": "x", "llm_model": "m"}),
            ToolUseBlock(id="t2", name="mcp__intervals__schedule_workout", input={"date": "2026-11-07"}),
            ToolUseBlock(id="t3", name="mcp__intervals__get_plan", input={})], model="m")
        yield UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="ok", is_error=False),
                                   ToolResultBlock(tool_use_id="t2", content="denied", is_error=True),
                                   ToolResultBlock(tool_use_id="t3", content="plan", is_error=False)])
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False,
                            num_turns=2, session_id="s", total_cost_usd=0.0, result="Done")

    monkeypatch.setattr(agent_mod, "query", fake_query)
    rt = build_runtime(cfg, journal=j)
    reply = asyncio.run(rt.agent.ask("move Thursday's ramp test to Friday", chat_id=7))
    posts = [c for c in calls if c.method == "POST"]
    assert [w[0] for w in reply.writes] == ["update_planned_workout"] and len(posts) == 1
    assert b"Intervals: update_planned_workout" in posts[0].content and b"llm_model" not in posts[0].content
