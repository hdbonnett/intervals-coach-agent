"""SQLite persistence: chat sessions, reminders, athlete notes, job runs."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    chat_id     INTEGER PRIMARY KEY,
    session_id  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    due_at      TEXT NOT NULL,          -- UTC ISO-8601
    text        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT 'chat',
    dedupe_key  TEXT UNIQUE,
    created_at  TEXT NOT NULL,
    sent_at     TEXT,
    cancelled   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,          -- 'chat' or job name
    started_at  TEXT NOT NULL,
    status      TEXT NOT NULL,
    session_id  TEXT,
    cost_usd    REAL,
    num_turns   INTEGER,
    detail      TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Reminder:
    id: int
    chat_id: int
    due_at: datetime
    text: str
    source: str
    dedupe_key: str | None


class Store:
    def __init__(self, path: Path | str):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    # --- sessions -------------------------------------------------------
    def get_session(self, chat_id: int, max_age_hours: float) -> str | None:
        row = self._exec("SELECT session_id, updated_at FROM sessions WHERE chat_id=?", (chat_id,)).fetchone()
        if not row:
            return None
        age = utcnow() - datetime.fromisoformat(row["updated_at"])
        if age.total_seconds() > max_age_hours * 3600:
            return None
        return row["session_id"]

    def set_session(self, chat_id: int, session_id: str) -> None:
        self._exec(
            "INSERT INTO sessions(chat_id, session_id, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET session_id=excluded.session_id, updated_at=excluded.updated_at",
            (chat_id, session_id, utcnow().isoformat()),
        )

    def clear_session(self, chat_id: int) -> None:
        self._exec("DELETE FROM sessions WHERE chat_id=?", (chat_id,))

    # --- reminders ------------------------------------------------------
    def add_reminder(self, chat_id: int, due_at: datetime, text: str,
                     source: str = "chat", dedupe_key: str | None = None) -> int | None:
        """Returns the new id, or None if dedupe_key already exists."""
        if due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")
        try:
            cur = self._exec(
                "INSERT INTO reminders(chat_id, due_at, text, source, dedupe_key, created_at) VALUES(?,?,?,?,?,?)",
                (chat_id, due_at.astimezone(timezone.utc).isoformat(), text, source, dedupe_key, utcnow().isoformat()),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def pending_reminders(self, chat_id: int | None = None) -> list[Reminder]:
        sql = "SELECT * FROM reminders WHERE sent_at IS NULL AND cancelled=0"
        params: tuple = ()
        if chat_id is not None:
            sql += " AND chat_id=?"
            params = (chat_id,)
        return [self._row_to_reminder(r) for r in self._exec(sql + " ORDER BY due_at", params).fetchall()]

    def due_reminders(self, now: datetime | None = None) -> list[Reminder]:
        now = (now or utcnow()).astimezone(timezone.utc).isoformat()
        rows = self._exec(
            "SELECT * FROM reminders WHERE sent_at IS NULL AND cancelled=0 AND due_at<=? ORDER BY due_at", (now,)
        ).fetchall()
        return [self._row_to_reminder(r) for r in rows]

    def mark_sent(self, reminder_id: int) -> None:
        self._exec("UPDATE reminders SET sent_at=? WHERE id=?", (utcnow().isoformat(), reminder_id))

    def cancel_reminder(self, reminder_id: int) -> bool:
        cur = self._exec("UPDATE reminders SET cancelled=1 WHERE id=? AND sent_at IS NULL AND cancelled=0", (reminder_id,))
        return cur.rowcount > 0

    @staticmethod
    def _row_to_reminder(r: sqlite3.Row) -> Reminder:
        return Reminder(r["id"], r["chat_id"], datetime.fromisoformat(r["due_at"]), r["text"], r["source"], r["dedupe_key"])

    # --- notes (durable athlete facts the agent learns in chat) ----------
    def add_note(self, text: str) -> int:
        return self._exec("INSERT INTO notes(text, created_at) VALUES(?,?)", (text, utcnow().isoformat())).lastrowid

    def list_notes(self) -> list[tuple[int, str]]:
        return [(r["id"], r["text"]) for r in self._exec("SELECT id, text FROM notes ORDER BY id").fetchall()]

    def delete_note(self, note_id: int) -> bool:
        return self._exec("DELETE FROM notes WHERE id=?", (note_id,)).rowcount > 0

    # --- run log --------------------------------------------------------
    def log_run(self, kind: str, status: str, session_id: str | None = None,
                cost_usd: float | None = None, num_turns: int | None = None, detail: str | None = None) -> None:
        self._exec(
            "INSERT INTO runs(kind, started_at, status, session_id, cost_usd, num_turns, detail) VALUES(?,?,?,?,?,?,?)",
            (kind, utcnow().isoformat(), status, session_id, cost_usd, num_turns, detail),
        )

    def cost_since(self, since: datetime) -> float:
        row = self._exec("SELECT COALESCE(SUM(cost_usd),0) AS c FROM runs WHERE started_at>=?",
                         (since.astimezone(timezone.utc).isoformat(),)).fetchone()
        return float(row["c"])
