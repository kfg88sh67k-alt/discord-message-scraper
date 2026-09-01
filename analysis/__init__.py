"""Analysis toolkit for output/messages.db.

CLI — no coding needed:
    python3 analysis.py                     # default report: pies + timelines
    python3 -m analysis stats
    python3 -m analysis activity --by month
    python3 -m analysis top-authors --limit 10
    python3 -m analysis reactions
    python3 -m analysis search "hello"

Import — for notebooks / scripts:
    from analysis import MessageDB, top_authors
    rows = top_authors()          # list[sqlite3.Row]

Every function returns list[sqlite3.Row] so results compose.
"""

from .cli import main
from .db import REAL_MESSAGES, connect, q
from .messagedb import MessageDB
from .queries import (
    activity,
    attachments,
    emoji_use,
    mentions,
    most_replied,
    reactions,
    search,
    top_authors,
    top_words,
)
from .report import report

__all__ = [
    "REAL_MESSAGES",
    "MessageDB",
    "activity",
    "attachments",
    "connect",
    "emoji_use",
    "main",
    "mentions",
    "most_replied",
    "q",
    "reactions",
    "report",
    "search",
    "top_authors",
    "top_words",
]
