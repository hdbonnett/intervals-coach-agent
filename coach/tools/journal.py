"""journal_add: lets the agent record a decision in the shared journal (only when configured)."""
from __future__ import annotations

from claude_agent_sdk import tool


def build(ctx):
    from . import text_result

    if ctx.journal is None:
        return []

    @tool(
        "journal_add",
        "Append one entry to the shared training journal that the athlete also reads and writes from "
        "claude.ai. Use for decisions, agreed plan changes, and things the athlete reports that matter "
        "for training. Summarise in your own words; keep each field to a sentence or two.",
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "A few words, e.g. 'Ramp test timing'"},
                "summary": {"type": "string", "description": "What was discussed or reported"},
                "decisions": {"type": "string", "description": "What was decided, if anything"},
                "followups": {"type": "string", "description": "Anything left to do or check later"},
            },
            "required": ["topic", "summary"],
        },
    )
    async def journal_add(args):
        ok = await ctx.journal.safe_append(args["topic"], args["summary"],
                                           args.get("decisions", ""), args.get("followups", ""))
        return text_result("Logged to the journal." if ok else "Could not reach the journal; nothing was logged.",
                           not ok)

    return [journal_add]
