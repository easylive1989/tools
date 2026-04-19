import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id        TEXT PRIMARY KEY,
    last_processed_id TEXT,
    updated_at        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id       TEXT PRIMARY KEY,
    parent_msg_id   TEXT NOT NULL,
    cli_session_id  TEXT,
    cli_kind        TEXT NOT NULL,
    created_at      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    message_id   TEXT PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    thread_id    TEXT,
    author_id    TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_at   INTEGER NOT NULL,
    processed_at INTEGER
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id   TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL,
    started_at   INTEGER,
    finished_at  INTEGER,
    error_text   TEXT,
    FOREIGN KEY (message_id) REFERENCES messages(message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_created
    ON messages(channel_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_thread
    ON messages(thread_id, created_at);
"""


@dataclass(frozen=True)
class ThreadRow:
    thread_id: str
    parent_msg_id: str
    cli_session_id: str | None
    cli_kind: str
    created_at: int


@dataclass(frozen=True)
class MessageRow:
    message_id: str
    channel_id: str
    thread_id: str | None
    author_id: str
    content: str
    created_at: int
    processed_at: int | None


class Storage:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- channels ------------------------------------------------------

    def get_last_processed_id(self, channel_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT last_processed_id FROM channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        return row[0] if row else None

    def update_last_processed_id(self, channel_id: str, message_id: str) -> None:
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO channels(channel_id, last_processed_id, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                last_processed_id = CASE
                    WHEN channels.last_processed_id IS NULL
                      OR CAST(excluded.last_processed_id AS INTEGER)
                         > CAST(channels.last_processed_id AS INTEGER)
                    THEN excluded.last_processed_id
                    ELSE channels.last_processed_id
                END,
                updated_at = excluded.updated_at
            """,
            (channel_id, message_id, now),
        )

    # --- threads -------------------------------------------------------

    def upsert_thread(
        self,
        thread_id: str,
        parent_msg_id: str,
        cli_kind: str,
        cli_session_id: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO threads(thread_id, parent_msg_id, cli_session_id, cli_kind, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO NOTHING
            """,
            (thread_id, parent_msg_id, cli_session_id, cli_kind, int(time.time())),
        )

    def set_cli_session(self, thread_id: str, cli_session_id: str) -> None:
        self._conn.execute(
            "UPDATE threads SET cli_session_id = ? WHERE thread_id = ?",
            (cli_session_id, thread_id),
        )

    def get_thread(self, thread_id: str) -> ThreadRow | None:
        row = self._conn.execute(
            """
            SELECT thread_id, parent_msg_id, cli_session_id, cli_kind, created_at
            FROM threads WHERE thread_id = ?
            """,
            (thread_id,),
        ).fetchone()
        return ThreadRow(*row) if row else None

    def list_threads(self) -> list[ThreadRow]:
        rows = self._conn.execute(
            """
            SELECT thread_id, parent_msg_id, cli_session_id, cli_kind, created_at
            FROM threads ORDER BY created_at ASC
            """
        ).fetchall()
        return [ThreadRow(*r) for r in rows]

    # --- messages ------------------------------------------------------

    def record_message(
        self,
        message_id: str,
        channel_id: str,
        thread_id: str | None,
        author_id: str,
        content: str,
        created_at: int,
    ) -> bool:
        """Idempotent insert. Returns True if newly inserted, False if already existed."""
        cur = self._conn.execute(
            """
            INSERT INTO messages(message_id, channel_id, thread_id, author_id, content, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(message_id) DO NOTHING
            """,
            (message_id, channel_id, thread_id, author_id, content, created_at),
        )
        return cur.rowcount > 0

    def mark_processed(self, message_id: str) -> None:
        self._conn.execute(
            "UPDATE messages SET processed_at = ? WHERE message_id = ?",
            (int(time.time()), message_id),
        )

    def is_processed(self, message_id: str) -> bool:
        row = self._conn.execute(
            "SELECT processed_at FROM messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        return bool(row and row[0] is not None)

    def last_message_id_in_thread(self, thread_id: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT message_id FROM messages
            WHERE thread_id = ?
            ORDER BY created_at DESC, message_id DESC
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        return row[0] if row else None

    def unprocessed_messages(self) -> Iterator[MessageRow]:
        rows = self._conn.execute(
            """
            SELECT message_id, channel_id, thread_id, author_id, content, created_at, processed_at
            FROM messages
            WHERE processed_at IS NULL
            ORDER BY created_at ASC, message_id ASC
            """
        ).fetchall()
        for r in rows:
            yield MessageRow(*r)

    # --- tasks ---------------------------------------------------------

    def start_task(self, message_id: str) -> None:
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO tasks(message_id, status, started_at)
            VALUES(?, 'running', ?)
            ON CONFLICT(message_id) DO UPDATE SET
                status = 'running',
                started_at = excluded.started_at,
                finished_at = NULL,
                error_text = NULL
            """,
            (message_id, now),
        )

    def finish_task(self, message_id: str, error: str | None = None) -> None:
        now = int(time.time())
        status = "error" if error else "done"
        self._conn.execute(
            """
            UPDATE tasks SET status = ?, finished_at = ?, error_text = ?
            WHERE message_id = ?
            """,
            (status, now, error, message_id),
        )
