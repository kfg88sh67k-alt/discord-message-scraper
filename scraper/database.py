"""SQLite layer: schema, resume metadata, batch inserts, stats."""

from __future__ import annotations

import sqlite3

from scraper.config import DB_PATH, OUTPUT_DIR
from scraper.transform import to_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_username TEXT,
    content TEXT,
    created_at TEXT NOT NULL,
    edited_at TEXT,
    reply_to_id TEXT,
    has_attachments INTEGER DEFAULT 0,
    type INTEGER,                  -- 0=default, 19=reply, 3=call, 7=join, ...
    pinned INTEGER DEFAULT 0,
    raw TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_created ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_author ON messages (author_id);
CREATE INDEX IF NOT EXISTS idx_type ON messages (type);
"""

INSERT_SQL = """
INSERT OR IGNORE INTO messages
  (id, channel_id, author_id, author_username, content,
   created_at, edited_at, reply_to_id, has_attachments, type, pinned, raw)
VALUES
  (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def open_db() -> sqlite3.Connection:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.executescript(INDEXES)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring older databases up to the current schema; backfill new columns
    from the raw JSON so no re-scrape is needed."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "type" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN type INTEGER")
    if "pinned" not in cols:
        conn.execute("ALTER TABLE messages ADD COLUMN pinned INTEGER DEFAULT 0")
    conn.execute(
        "UPDATE messages SET type = json_extract(raw, '$.type') WHERE type IS NULL"
    )
    conn.execute(
        "UPDATE messages SET pinned = json_extract(raw, '$.pinned') WHERE pinned IS NULL"
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def insert_batch(conn: sqlite3.Connection, batch: list[dict]) -> int:
    """Insert one batch of API messages; returns how many rows were new."""
    before = conn.total_changes
    conn.executemany(INSERT_SQL, [to_row(m) for m in batch])
    conn.commit()
    return conn.total_changes - before


def stats(conn: sqlite3.Connection) -> tuple[int, int, str, str]:
    """(total messages, distinct authors, oldest timestamp, newest timestamp)."""
    return conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT author_id), MIN(created_at), MAX(created_at) FROM messages"
    ).fetchone()
