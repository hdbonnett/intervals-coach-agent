"""Scheduled agent jobs (from config.yaml) plus the reminder dispatcher."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from .config import JobConfig
from .telegram_io import send_text, typing

log = logging.getLogger(__name__)


def render_prompt(cfg, job: JobConfig, attempt: int) -> str:
    """Fill {{TODAY}}, {{WEEKDAY}}, {{ATTEMPT_NOTE}} in a job's prompt file."""
    now = datetime.now(cfg.timezone)
    if attempt >= job.max_retries:
        attempt_note = ("This is the FINAL attempt: report with whatever data is available "
                        "and say plainly what is missing.")
    elif job.retry_token:
        attempt_note = (f"If last night's sleep/wellness record for today is not in Intervals yet, "
                        f"reply with exactly {job.retry_token} and nothing else.")
    else:
        attempt_note = ""
    text = cfg.resolve(job.prompt_file).read_text()
    return (text.replace("{{TODAY}}", now.strftime("%Y-%m-%d"))
                .replace("{{WEEKDAY}}", now.strftime("%A"))
                .replace("{{ATTEMPT_NOTE}}", attempt_note))


class Scheduler:
    def __init__(self, runtime):
        self.rt = runtime
        self.cfg = runtime.cfg
        self.sched = AsyncIOScheduler(timezone=self.cfg.timezone)
        self.jobs: dict[str, JobConfig] = {j.name: j for j in self.cfg.jobs}

    def start(self) -> None:
        for job in self.jobs.values():
            if not job.enabled:
                continue
            self.sched.add_job(self._run_job, CronTrigger.from_crontab(job.cron, timezone=self.cfg.timezone),
                               args=[job.name], id=job.name, coalesce=True, misfire_grace_time=3600,
                               max_instances=1)
        self.sched.add_job(self._dispatch_reminders, "interval", seconds=60, id="_reminders",
                           coalesce=True, max_instances=1)
        self.sched.start()
        log.info("Scheduler started:\n%s", self.describe())

    def describe(self) -> str:
        lines = []
        for job in self.jobs.values():
            sj = self.sched.get_job(job.name)
            nxt = sj.next_run_time.strftime("%a %d %b %H:%M") if sj and sj.next_run_time else "disabled"
            lines.append(f"{job.name}: '{job.cron}' → next {nxt}")
        return "\n".join(lines) or "No jobs configured."

    async def run_job_now(self, name: str, chat_id: int | None = None) -> None:
        await self._run_job(name, chat_id=chat_id, manual=True)

    # ------------------------------------------------------------------
    def _render_prompt(self, job: JobConfig, attempt: int) -> str:
        return render_prompt(self.cfg, job, attempt)

    async def _run_job(self, name: str, chat_id: int | None = None, attempt: int = 0, manual: bool = False) -> None:
        job = self.jobs.get(name)
        if job is None:
            log.error("Unknown job %s", name)
            return
        chat_id = chat_id or self.cfg.default_chat_id
        if manual:  # an on-demand run always reports, never defers
            attempt = job.max_retries
        bot = self.rt.app.bot
        agent = self.rt.agent
        log.info("Running job %s (attempt %d)", name, attempt)

        async with agent.lock_for(chat_id), typing(bot, chat_id) if manual else _null():
            try:
                reply = await agent.ask(self._render_prompt(job, attempt), chat_id=chat_id,
                                        model=job.model, continue_session=False, kind=name)
            except Exception as e:  # noqa: BLE001
                log.exception("Job %s failed", name)
                await bot.send_message(chat_id, f"⚠️ {name} failed: {type(e).__name__}: {e}")
                return

        text = reply.text.strip()
        if job.retry_token and text.startswith(job.retry_token) and attempt < job.max_retries:
            when = datetime.now(self.cfg.timezone) + timedelta(minutes=job.retry_minutes)
            log.info("Job %s: data not ready, retrying at %s", name, when)
            self.sched.add_job(self._run_job, DateTrigger(when), args=[name, chat_id, attempt + 1],
                               id=f"{name}_retry", replace_existing=True)
            return
        if job.silent_token and text.startswith(job.silent_token):
            if manual:
                await bot.send_message(chat_id, "Nothing new to report.")
            return
        # Make the job's conversation the chat's current one, so a reply like "why amber?" follows on.
        if reply.session_id:
            self.rt.store.set_session(chat_id, reply.session_id)
        await send_text(bot, chat_id, text)
        if job.journal_topic and self.rt.agent.journal and not reply.is_error:
            await self.rt.agent.journal.safe_append(job.journal_topic, text)

    async def _dispatch_reminders(self) -> None:
        for r in self.rt.store.due_reminders():
            try:
                await send_text(self.rt.app.bot, r.chat_id, f"⏰ {r.text}")
                self.rt.store.mark_sent(r.id)
            except Exception:  # noqa: BLE001 - retry next minute
                log.exception("Failed to send reminder %s", r.id)


class _null:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False
