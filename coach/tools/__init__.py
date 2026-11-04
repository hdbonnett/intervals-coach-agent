"""In-process tools exposed to Claude as the `coach` MCP server.

To add a capability: create a module here with a `build(ctx) -> list[SdkMcpTool]`
function and add it to TOOL_MODULES. Tools appear to Claude as mcp__coach__<name>.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from claude_agent_sdk import create_sdk_mcp_server

from ..store import Store
from . import journal, notes, reminders

TOOL_MODULES = [reminders, notes, journal]


@dataclass
class ToolContext:
    store: Store
    tz: ZoneInfo
    default_chat_id: int
    journal: Any = None          # coach.journal.Journal when configured


def text_result(text: str, is_error: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["is_error"] = True
    return out


def build_coach_server(ctx: ToolContext):
    tools = []
    for mod in TOOL_MODULES:
        tools.extend(mod.build(ctx))
    return create_sdk_mcp_server(name="coach", version="0.1.0", tools=tools)
