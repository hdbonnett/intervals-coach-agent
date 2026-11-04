"""Athlete notes: durable facts learned in chat, injected into every system prompt."""
from __future__ import annotations

from claude_agent_sdk import tool


def build(ctx):
    from . import text_result

    @tool(
        "remember_note",
        "Save a durable fact the athlete has stated (a preference, constraint, injury, schedule change) "
        "so future conversations know it. Only facts the athlete actually said; never your own inferences.",
        {"text": str},
    )
    async def remember_note(args):
        nid = ctx.store.add_note(args["text"].strip())
        return text_result(f"Saved note #{nid}.")

    @tool("list_notes", "List saved athlete notes with ids.", {})
    async def list_notes(args):
        notes = ctx.store.list_notes()
        return text_result("\n".join(f"#{i} {t}" for i, t in notes) if notes else "No notes saved.")

    @tool("forget_note", "Delete a saved athlete note by id (when the athlete says it no longer applies).", {"id": int})
    async def forget_note(args):
        ok = ctx.store.delete_note(int(args["id"]))
        return text_result("Deleted." if ok else "No note with that id.", not ok)

    return [remember_note, list_notes, forget_note]
