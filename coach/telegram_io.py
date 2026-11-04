"""Telegram front end: allow-listed chats, commands, free-text chat with the agent."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime

from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .formatting import md_to_tg_html, split_message

log = logging.getLogger(__name__)

COMMANDS = [
    ("brief", "Run the morning readiness check now"),
    ("plan", "What's coming up this week"),
    ("reminders", "List pending reminders"),
    ("notes", "List saved notes about you"),
    ("jobs", "Show scheduled jobs and next run times"),
    ("new", "Start a fresh conversation"),
    ("cost", "API spend today and this month"),
    ("help", "Show commands"),
]


async def send_text(bot, chat_id: int, text: str) -> None:
    """Send agent output as Telegram HTML, falling back to plain text if parsing fails."""
    for chunk in split_message(text):
        try:
            await bot.send_message(chat_id, md_to_tg_html(chunk), parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
        except BadRequest as e:
            log.warning("HTML send failed (%s); sending plain text", e)
            await bot.send_message(chat_id, chunk, disable_web_page_preview=True)


@contextlib.asynccontextmanager
async def typing(bot, chat_id: int):
    async def loop():
        while True:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(4.5)
    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


class TelegramFrontEnd:
    def __init__(self, app: Application, runtime):
        self.app = app
        self.rt = runtime  # coach.main.Runtime: cfg, store, agent, scheduler
        allowed = filters.Chat(chat_id=runtime.cfg.allowed_chat_ids)

        # /whoami is open so you can discover your chat id during setup; it reveals nothing else.
        app.add_handler(CommandHandler("whoami", self.whoami))
        app.add_handler(CommandHandler(["start", "help"], self.help, filters=allowed))
        app.add_handler(CommandHandler("brief", self.brief, filters=allowed))
        app.add_handler(CommandHandler("plan", self.plan, filters=allowed))
        app.add_handler(CommandHandler("reminders", self.reminders, filters=allowed))
        app.add_handler(CommandHandler("notes", self.notes, filters=allowed))
        app.add_handler(CommandHandler("jobs", self.jobs, filters=allowed))
        app.add_handler(CommandHandler("new", self.new, filters=allowed))
        app.add_handler(CommandHandler("cost", self.cost, filters=allowed))
        app.add_handler(MessageHandler(allowed & filters.TEXT & ~filters.COMMAND, self.chat))
        app.add_handler(MessageHandler(~allowed, self.reject))
        app.add_error_handler(self.on_error)

    async def register_commands(self) -> None:
        await self.app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])

    # ------------------------------------------------------------------
    async def run_agent(self, chat_id: int, prompt: str, **kw) -> None:
        agent = self.rt.agent
        async with agent.lock_for(chat_id), typing(self.app.bot, chat_id):
            try:
                reply = await agent.ask(prompt, chat_id=chat_id, **kw)
            except Exception as e:  # noqa: BLE001 - report to the user, keep the bot alive
                log.exception("Agent call failed")
                await self.app.bot.send_message(chat_id, f"⚠️ Agent error: {type(e).__name__}: {e}")
                return
        if reply.session_id:
            self.rt.store.set_session(chat_id, reply.session_id)
        await send_text(self.app.bot, chat_id, reply.text)

    async def chat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.run_agent(update.effective_chat.id, update.message.text)

    async def plan(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.run_agent(update.effective_chat.id,
                             "What's on my plan for the next 7 days? Flag any tests, races or key sessions, "
                             "and anything worth adjusting given my recent recovery.")

    async def brief(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.rt.scheduler.run_job_now("morning_briefing", chat_id=update.effective_chat.id)

    async def reminders(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tz = self.rt.cfg.timezone
        items = self.rt.store.pending_reminders()
        text = "\n".join(f"#{r.id} {r.due_at.astimezone(tz):%a %d %b %H:%M} — {r.text}" for r in items) \
            or "No pending reminders."
        await update.message.reply_text(text)

    async def notes(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        notes = self.rt.store.list_notes()
        await update.message.reply_text("\n".join(f"#{i} {t}" for i, t in notes) or "No notes saved.")

    async def jobs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(self.rt.scheduler.describe())

    async def new(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        self.rt.store.clear_session(update.effective_chat.id)
        await update.message.reply_text("Fresh conversation started.")

    async def cost(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tz = self.rt.cfg.timezone
        now = datetime.now(tz)
        day = self.rt.store.cost_since(now.replace(hour=0, minute=0, second=0, microsecond=0))
        month = self.rt.store.cost_since(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        await update.message.reply_text(f"API spend — today: US${day:.2f}, this month: US${month:.2f}")

    async def help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Ask me anything about your training, or:\n" + "\n".join(f"/{c} — {d}" for c, d in COMMANDS))

    async def whoami(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(f"Your chat id is {update.effective_chat.id}")

    async def reject(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        log.warning("Ignored message from non-allow-listed chat %s", update.effective_chat.id if update.effective_chat else "?")

    async def on_error(self, update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Telegram handler error", exc_info=ctx.error)
