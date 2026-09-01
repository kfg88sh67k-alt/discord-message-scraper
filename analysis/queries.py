"""Ready-made analyses. Each takes an open connection, returns rows."""

from __future__ import annotations

import re
from collections import Counter

from .db import REAL_MESSAGES, q


def activity(conn, by: str = "month", author: str | None = None, include_system: bool = False):
    fmt = {"month": "%Y-%m", "day": "%Y-%m-%d", "hour": "%H"}[by]
    where = [] if include_system else [f"({REAL_MESSAGES})"]
    params: tuple = ()
    if author:
        where.append("author_username = ? COLLATE NOCASE")
        params = (author,)
    sql = f"""
      SELECT strftime('{fmt}', created_at) AS bucket, COUNT(*) AS messages
      FROM messages
      {'WHERE ' + ' AND '.join(where) if where else ''}
      GROUP BY bucket ORDER BY bucket
    """
    return q(conn, sql, params)


def top_authors(conn, limit: int = 20, include_system: bool = False):
    where = "" if include_system else f"WHERE {REAL_MESSAGES}"
    return q(conn, f"""
      SELECT author_id, author_username, COUNT(*) AS messages,
             SUM(has_attachments) AS attachments,
             SUM(CASE WHEN reply_to_id IS NOT NULL THEN 1 ELSE 0 END) AS replies,
             MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
      FROM messages {where}
      GROUP BY author_id ORDER BY messages DESC LIMIT ?
    """, (limit,))


def reactions(conn, limit: int = 20):
    return q(conn, f"""
      SELECT json_extract(r.value, '$.emoji.name') AS emoji,
             SUM(json_extract(r.value, '$.count')) AS uses,
             COUNT(*) AS on_messages
      FROM messages, json_each(messages.raw, '$.reactions') r
      GROUP BY emoji ORDER BY uses DESC LIMIT ?
    """, (limit,))


def attachments(conn, limit: int = 20):
    return q(conn, """
      SELECT json_extract(j.value, '$.content_type') AS content_type,
             COUNT(*) AS n
      FROM messages, json_each(messages.raw, '$.attachments') j
      GROUP BY content_type ORDER BY n DESC LIMIT ?
    """, (limit,))


def mentions(conn, limit: int = 20):
    # NOTE: qualify messages.type — json_each also exposes a `type` column.
    return q(conn, """
      SELECT json_extract(j.value, '$.username') AS mentioned,
             COUNT(*) AS n
      FROM messages, json_each(messages.raw, '$.mentions') j
      WHERE messages.type IN (0, 19)
      GROUP BY mentioned ORDER BY n DESC LIMIT ?
    """, (limit,))


def most_replied(conn, limit: int = 20):
    return q(conn, f"""
      SELECT m.author_username, m.content, COUNT(r.id) AS reply_count
      FROM messages m
      JOIN messages r ON r.reply_to_id = m.id
      WHERE ({REAL_MESSAGES.replace('type', 'm.type')})
      GROUP BY m.id ORDER BY reply_count DESC LIMIT ?
    """, (limit,))


def search(conn, text: str, limit: int = 50):
    escaped = text.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return q(conn, f"""
      SELECT created_at, author_username, content
      FROM messages
      WHERE ({REAL_MESSAGES}) AND content LIKE ? ESCAPE '\\'
      ORDER BY created_at LIMIT ?
    """, (f"%{escaped}%", limit))


def top_words(conn, limit: int = 30, author: str | None = None, min_len: int = 3):
    where = [f"({REAL_MESSAGES})"]
    params: list = []
    if author:
        where.append("author_username = ? COLLATE NOCASE")
        params.append(author)
    words: Counter = Counter()
    for (content,) in conn.execute(
        f"SELECT content FROM messages WHERE {' AND '.join(where)}", params
    ):
        words.update(w for w in re.findall(r"[a-zA-Z']+", content.lower()) if len(w) >= min_len)
    return words.most_common(limit)


EMOJI_RE = re.compile(
    r"<a?:\w+:\d+>"                       # custom :name:id
    r"|[\U0001F1E6-\U0001F1FF]{2}"        # flag = regional-indicator pair
    r"|[\U0001F000-\U0001FAFF\u2600-\u27BF]"  # single emoji
)


def emoji_use(conn, limit: int = 30, author: str | None = None):
    """Custom emoji (and unicode emoji) used directly in message text."""
    where = [f"({REAL_MESSAGES})", "content LIKE '%'"]
    params: list = []
    if author:
        where.append("author_username = ? COLLATE NOCASE")
        params.append(author)
    counts: Counter = Counter()
    for (content,) in conn.execute(
        f"SELECT content FROM messages WHERE {' AND '.join(where)}", params
    ):
        counts.update(m.group(0) for m in EMOJI_RE.finditer(content))
    return counts.most_common(limit)
