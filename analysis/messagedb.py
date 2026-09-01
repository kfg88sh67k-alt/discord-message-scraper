"""MessageDB: high-level wrapper for developing your own analysis."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import queries
from .db import REAL_MESSAGES
from scraper.config import DB_PATH


class MessageDB:
    """High-level wrapper for developing your own analysis.

    from analysis import MessageDB
    db = MessageDB()

    db.messages()                                  # every message as a parsed dict
    db.messages(where="author_username = ?", params=("joyt",))
    db.query("SELECT ... FROM messages ...")       # raw SQL, still comfortable
    db.scalar("SELECT COUNT(*) FROM messages")
    db.frame()                                     # pandas DataFrame (if installed)

    Plus the ready-made analyses as methods: db.top_authors(), db.activity(),
    db.reactions(), db.attachments(), db.mentions(), db.most_replied(),
    db.search("text"), db.top_words(), db.emoji_use().
    """

    def __init__(self, path: str | Path = DB_PATH, read_only: bool = True):
        uri = f"file:{path}?mode=ro" if read_only else f"file:{path}"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- generic building blocks ---

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()) -> sqlite3.Row:
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: tuple = ()):
        return self.conn.execute(sql, params).fetchone()[0]

    def messages(
        self,
        where: str = "",
        params: tuple = (),
        include_system: bool = False,
        parse_raw: bool = True,
    ) -> list[dict]:
        """Messages as parsed dicts (via json.loads on raw). Filter with a
        SQL `where` clause, e.g. `author_username = ?` + params."""
        clauses = []
        if not include_system:
            clauses.append(f"({REAL_MESSAGES})")
        if where:
            clauses.append(f"({where})")
        sql = "SELECT raw FROM messages"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.conn.execute(sql, params).fetchall()
        if parse_raw:
            return [json.loads(r[0]) for r in rows]
        return [dict(self.one("SELECT * FROM messages WHERE raw = ?", (r[0],))) for r in rows]

    def frame(self, sql: str | None = None, params: tuple = ()):
        """pandas DataFrame — requires `pip install pandas`."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pip install pandas to use .frame()") from None
        if sql is None:
            return pd.DataFrame(self.messages())
        return pd.read_sql_query(sql, self.conn, params=params)

    # --- ready-made analyses (same as the functions in queries.py) ---

    def activity(self, by="month", author=None, include_system=False):
        return queries.activity(self.conn, by, author, include_system)

    def top_authors(self, limit=20, include_system=False):
        return queries.top_authors(self.conn, limit, include_system)

    def reactions(self, limit=20):
        return queries.reactions(self.conn, limit)

    def attachments(self, limit=20):
        return queries.attachments(self.conn, limit)

    def mentions(self, limit=20):
        return queries.mentions(self.conn, limit)

    def most_replied(self, limit=20):
        return queries.most_replied(self.conn, limit)

    def search(self, text, limit=50):
        return queries.search(self.conn, text, limit)

    def top_words(self, limit=30, author=None, min_len=3):
        return queries.top_words(self.conn, limit, author, min_len)

    def emoji_use(self, limit=30, author=None):
        return queries.emoji_use(self.conn, limit, author)
