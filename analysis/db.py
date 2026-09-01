"""Low-level DB access: read-only connection, row helper, message filter."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from scraper.config import DB_PATH

REAL_MESSAGES = "type IN (0, 19)"  # excludes calls, joins, pin notices, ...


def connect(read_only: bool = True) -> sqlite3.Connection:
    if not Path(DB_PATH).exists():
        sys.exit(f"No database at {DB_PATH} — run `python3 main.py` first.")
    uri = f"file:{DB_PATH}?mode=ro" if read_only else f"file:{DB_PATH}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()
