"""Convert Discord API message objects into DB row tuples."""

from __future__ import annotations

import json


def to_row(m: dict) -> tuple:
    """Map one API message object onto the `messages` table columns.

    The untouched payload is kept in `raw` so reactions/embeds/mentions can be
    extracted later without re-scraping.
    """
    return (
        m["id"],
        m["channel_id"],
        m["author"]["id"],
        m["author"].get("username") or m["author"].get("global_name"),
        m.get("content") or "",
        m["timestamp"],
        m.get("edited_timestamp"),
        # `referenced_message` is absent when the parent was deleted, but
        # `message_reference.message_id` still points at it.
        (m.get("referenced_message") or m.get("message_reference") or {}).get(
            "message_id" if "referenced_message" not in m else "id"
        ),
        1 if m.get("attachments") else 0,
        m.get("type"),
        1 if m.get("pinned") else 0,
        json.dumps(m),
    )
