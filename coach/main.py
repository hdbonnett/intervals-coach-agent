"""Entry point: wires config, store, tools, agent, Telegram and the scheduler."""
from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

import httpx
from telegram.ext import Application
from telegram.request import HTTPXRequest

from .agent import Agent
from .config import Config, load_config
from .journal import Journal
from .scheduler import Scheduler, render_prompt
from .store import Store
from .telegram_io import TelegramFrontEnd
from .tools import ToolContext, build_coach_server


@dataclass
class Runtime:
    cfg: Config
    store: Store
    agent: Agent
    app: Application | None = None
    scheduler: Scheduler | None = None
    frontend: TelegramFrontEnd | None = None


def build_runtime(cfg: Config, journal=None) -> Runtime:
    store = Store(cfg.db_path)
    if journal is None and cfg.journal is not None:
        journal = Journal(cfg.journal, cfg.timezone)
    server = build_coach_server(ToolContext(store=store, tz=cfg.timezone,
                                            default_chat_id=cfg.default_chat_id, journal=journal))
    return Runtime(cfg=cfg, store=store, agent=Agent(cfg, store, server, journal))


def telegram_request(cfg: Config, pool_size: int) -> HTTPXRequest:
    """HTTP client for the Telegram Bot API, with configurable timeouts, proxy and IPv4-only mode."""
    extra = {}
    if cfg.tg_ipv4_only:
        # Binding to 0.0.0.0 makes every connection IPv4: avoids hangs on hosts whose IPv6
        # route is advertised but broken (Python, unlike curl, does not fall back quickly).
        extra["transport"] = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    return HTTPXRequest(
        connection_pool_size=pool_size,
        connect_timeout=cfg.tg_connect_timeout,
        read_timeout=cfg.tg_read_timeout,
        write_timeout=cfg.tg_read_timeout,
        pool_timeout=cfg.tg_connect_timeout,
        proxy=cfg.tg_proxy,
        httpx_kwargs=extra or None,
    )


def run() -> None:
    ap = argparse.ArgumentParser(description="Telegram training coach agent")
    ap.add_argument("-c", "--config", default=None,
                    help="Default: $COACH_CONFIG, ./config.yaml, or /etc/coach-agent/config.yaml")
    ap.add_argument("--ask", help="Ask one question on the console and exit (no Telegram)")
    ap.add_argument("--job", help="Render and run a job once, print the result, and exit (no Telegram)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    cfg = load_config(args.config)
    rt = build_runtime(cfg)

    if args.ask or args.job:
        asyncio.run(_console(rt, args))
        return

    app = (Application.builder().token(cfg.telegram_token)
           .request(telegram_request(cfg, pool_size=8))
           .get_updates_request(telegram_request(cfg, pool_size=1))
           .build())
    rt.app = app
    rt.frontend = TelegramFrontEnd(app, rt)
    rt.scheduler = Scheduler(rt)

    async def post_init(_: Application) -> None:
        await rt.frontend.register_commands()
        rt.scheduler.start()

    app.post_init = post_init
    # bootstrap_retries=-1: keep retrying the initial connection (e.g. network not up yet at boot)
    # instead of exiting after the first timeout.
    app.run_polling(allowed_updates=["message"], drop_pending_updates=True, bootstrap_retries=-1)


async def _console(rt: Runtime, args) -> None:
    """Smoke-test the agent and MCP wiring without Telegram."""
    if args.ask:
        prompt, model = args.ask, None
    else:
        job = next(j for j in rt.cfg.jobs if j.name == args.job)
        prompt = render_prompt(rt.cfg, job, attempt=job.max_retries)
        model = job.model
    reply = await rt.agent.ask(prompt, model=model, continue_session=False, kind="console")
    print(reply.text)
    print(f"\n--- session {reply.session_id}, turns {reply.num_turns}, cost US${reply.cost_usd or 0:.4f}")


if __name__ == "__main__":
    run()
