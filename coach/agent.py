"""Thin wrapper around the Claude Agent SDK: builds options, keeps per-chat sessions."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

from .config import Config
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class AgentReply:
    text: str
    session_id: str | None
    cost_usd: float | None
    num_turns: int | None
    is_error: bool = False
    # Successful calls to journal-logged tools: (short tool name, input arguments)
    writes: list[tuple[str, dict]] = field(default_factory=list)


class Agent:
    def __init__(self, cfg: Config, store: Store, coach_server, journal=None):
        self.cfg = cfg
        self.store = store
        self.coach_server = coach_server
        self.journal = journal
        self._locks: dict[int, asyncio.Lock] = {}
        cfg.workdir.mkdir(parents=True, exist_ok=True)

    def lock_for(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    # ------------------------------------------------------------------
    def system_prompt(self, journal_text: str = "") -> str:
        cfg = self.cfg
        base = (cfg.resolve(cfg.system_prompt_file).read_text()
                .replace("{{ATHLETE_NAME}}", cfg.athlete_name)
                .replace("{{LANGUAGE}}", cfg.language)
                .replace("{{TIMEZONE}}", cfg.timezone.key))
        parts = [base]
        for name in cfg.context_files:
            f = cfg.resolve(name)
            if f.exists():
                parts.append(f"\n\n# Context: {f.stem}\n\n{f.read_text()}")
        notes = self.store.list_notes()
        if notes:
            parts.append("\n\n# Notes saved from earlier chats (athlete-stated)\n"
                         + "\n".join(f"- (#{i}) {t}" for i, t in notes))
        if journal_text:
            parts.append(journal_text)
        return "".join(parts)

    def _options(self, model: str | None, resume: str | None, journal_text: str = "") -> ClaudeAgentOptions:
        servers = dict(self.cfg.mcp_servers)
        servers["coach"] = self.coach_server
        return ClaudeAgentOptions(
            system_prompt=self.system_prompt(journal_text),
            model=model or self.cfg.model,
            mcp_servers=servers,
            allowed_tools=self.cfg.allowed_tools,
            disallowed_tools=self.cfg.disallowed_tools,
            permission_mode="default",       # anything not in allowed_tools is denied headless
            max_turns=self.cfg.max_turns,
            max_budget_usd=self.cfg.max_budget_usd,
            resume=resume,
            cwd=str(self.cfg.workdir),
            setting_sources=self.cfg.setting_sources,  # default []: ignore host CLAUDE.md / settings
        )

    def _stamp(self, prompt: str) -> str:
        now = datetime.now(self.cfg.timezone)
        return f"[Now: {now:%A %d %B %Y %H:%M} {now.tzname()}, {self.cfg.timezone.key}]\n{prompt}"

    # ------------------------------------------------------------------
    async def ask(self, prompt: str, *, chat_id: int | None = None, model: str | None = None,
                  continue_session: bool = True, kind: str = "chat") -> AgentReply:
        resume = None
        if chat_id is not None and continue_session:
            resume = self.store.get_session(chat_id, self.cfg.session_max_age_hours)
        journal_text = await self.journal.context_block() if self.journal else ""
        try:
            reply = await self._run(self._stamp(prompt), model, resume, journal_text)
        except ClaudeSDKError as e:
            if resume:  # stale/missing session on disk: start fresh once
                log.warning("Resume of %s failed (%s); starting a new session", resume, e)
                reply = await self._run(self._stamp(prompt), model, None, journal_text)
            else:
                raise
        self.store.log_run(kind, "error" if reply.is_error else "ok", reply.session_id,
                           reply.cost_usd, reply.num_turns)
        await self._journal_writes(reply)
        return reply

    def _logged_tool(self, name: str) -> str | None:
        """Short name if `name` is an Intervals tool whose successful calls are journalled."""
        if not self.journal or not name.startswith("mcp__intervals__"):
            return None
        short = name.removeprefix("mcp__intervals__")
        return short if short in self.cfg.journal.log_tools else None

    async def _journal_writes(self, reply: AgentReply) -> None:
        """Deterministically log every successful change the agent made in Intervals."""
        for short, args in reply.writes:
            shown = {k: v for k, v in args.items() if k not in ("context", "llm_model", "confirmation_token")}
            await self.journal.safe_append(
                f"Intervals: {short}", json.dumps(shown, ensure_ascii=False, separators=(", ", ": ")))

    async def _run(self, prompt: str, model: str | None, resume: str | None,
                   journal_text: str = "") -> AgentReply:
        texts: list[str] = []
        result: ResultMessage | None = None
        pending: dict[str, tuple[str, dict]] = {}   # tool_use_id -> (short name, input)
        writes: list[tuple[str, dict]] = []
        async for msg in query(prompt=prompt, options=self._options(model, resume, journal_text)):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        texts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        short = self._logged_tool(block.name)
                        if short:
                            pending[block.id] = (short, dict(block.input or {}))
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in pending:
                        call = pending.pop(block.tool_use_id)
                        if not block.is_error:
                            writes.append(call)
            elif isinstance(msg, ResultMessage):
                result = msg
        if result is None:
            return AgentReply("\n".join(texts).strip() or "(no reply)", None, None, None, True, writes)
        text = (result.result or (texts[-1] if texts else "")).strip()
        if result.is_error and not text:
            text = f"Agent stopped: {result.subtype}"
        return AgentReply(text, result.session_id, result.total_cost_usd, result.num_turns,
                          result.is_error, writes)
