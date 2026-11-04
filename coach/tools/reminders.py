"""Reminder tools: the agent schedules messages; a dispatcher job sends them (no LLM call)."""
from __future__ import annotations

from datetime import datetime

from claude_agent_sdk import tool


def parse_local(when: str, tz) -> datetime:
    """Accept 'YYYY-MM-DD HH:MM' or ISO-8601; naive values are taken as local time."""
    dt = datetime.fromisoformat(when.strip().replace(" ", "T", 1) if "T" not in when else when.strip())
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def build(ctx):
    from . import text_result

    @tool(
        "add_reminder",
        "Schedule a Telegram reminder for the athlete. `when` is local time 'YYYY-MM-DD HH:MM'. "
        "Use `dedupe_key` (e.g. 'event:2026-11-25:tester-race:eve') for reminders derived from calendar "
        "events so repeated scans never create duplicates.",
        {
            "type": "object",
            "properties": {
                "when": {"type": "string", "description": "Local time, 'YYYY-MM-DD HH:MM'"},
                "text": {"type": "string", "description": "Message to send, short and self-contained"},
                "dedupe_key": {"type": "string"},
            },
            "required": ["when", "text"],
        },
    )
    async def add_reminder(args):
        try:
            due = parse_local(args["when"], ctx.tz)
        except ValueError:
            return text_result(f"Could not parse time '{args['when']}'. Use 'YYYY-MM-DD HH:MM'.", True)
        if due <= datetime.now(ctx.tz):
            return text_result(f"{due:%Y-%m-%d %H:%M} is in the past; not scheduled.", True)
        rid = ctx.store.add_reminder(ctx.default_chat_id, due, args["text"],
                                     source="agent", dedupe_key=args.get("dedupe_key"))
        if rid is None:
            return text_result(f"Already scheduled (dedupe_key {args.get('dedupe_key')}); nothing added.")
        return text_result(f"Reminder #{rid} set for {due:%a %d %b %H:%M}.")

    @tool("list_reminders", "List pending reminders with their ids and local due times.", {})
    async def list_reminders(args):
        items = ctx.store.pending_reminders()
        if not items:
            return text_result("No pending reminders.")
        lines = [f"#{r.id} {r.due_at.astimezone(ctx.tz):%a %d %b %H:%M} — {r.text}"
                 + (f" [key {r.dedupe_key}]" if r.dedupe_key else "") for r in items]
        return text_result("\n".join(lines))

    @tool("cancel_reminder", "Cancel a pending reminder by id.", {"id": int})
    async def cancel_reminder(args):
        ok = ctx.store.cancel_reminder(int(args["id"]))
        return text_result("Cancelled." if ok else "No pending reminder with that id.", not ok)

    return [add_reminder, list_reminders, cancel_reminder]
