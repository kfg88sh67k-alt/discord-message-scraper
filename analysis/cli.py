"""Command-line interface: python3 -m analysis <command> [options]."""

from __future__ import annotations

import argparse
import sqlite3

from .db import REAL_MESSAGES, connect
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


def _print_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("(no rows)")
        return
    cols = rows[0].keys()
    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(r[c]).ljust(w)[: w + 20] for c, w in zip(cols, widths)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd")  # no cmd = full report

    sub.add_parser("stats")
    p = sub.add_parser("activity"); p.add_argument("--by", default="month", choices=["month", "day", "hour"]); p.add_argument("--author"); p.add_argument("--include-system", action="store_true")
    p = sub.add_parser("top-authors"); p.add_argument("--limit", type=int, default=20); p.add_argument("--include-system", action="store_true")
    p = sub.add_parser("reactions"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("attachments"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("mentions"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("most-replied"); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("search"); p.add_argument("text"); p.add_argument("--limit", type=int, default=50)
    p = sub.add_parser("top-words"); p.add_argument("--limit", type=int, default=30); p.add_argument("--author"); p.add_argument("--min-len", type=int, default=3)
    p = sub.add_parser("emoji"); p.add_argument("--limit", type=int, default=30); p.add_argument("--author")
    p = sub.add_parser("report"); p.add_argument("--out", default=None); p.add_argument("--bucket", default="year", choices=["auto", "year", "month", "day"])

    args = parser.parse_args()
    if args.cmd is None or args.cmd == "report":
        report(args.out if args.cmd == "report" else None,
               args.bucket if args.cmd == "report" else "year")
        return

    conn = connect()

    if args.cmd == "stats":
        total, authors, first, last = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT author_id), MIN(created_at), MAX(created_at) FROM messages"
        ).fetchone()
        real = conn.execute(f"SELECT COUNT(*) FROM messages WHERE {REAL_MESSAGES}").fetchone()[0]
        _print_rows([{"messages": total, "real (non-system)": real, "authors": authors, "first": first, "last": last}])
    elif args.cmd == "activity":
        _print_rows(activity(conn, args.by, args.author, args.include_system))
    elif args.cmd == "top-authors":
        _print_rows(top_authors(conn, args.limit, args.include_system))
    elif args.cmd == "reactions":
        _print_rows(reactions(conn, args.limit))
    elif args.cmd == "attachments":
        _print_rows(attachments(conn, args.limit))
    elif args.cmd == "mentions":
        _print_rows(mentions(conn, args.limit))
    elif args.cmd == "most-replied":
        for r in most_replied(conn, args.limit):
            print(f"{r['reply_count']:3d}  {r['author_username']}: {(r['content'] or '')[:80]}")
    elif args.cmd == "search":
        for r in search(conn, args.text, args.limit):
            print(f"{r['created_at'][:16]}  {r['author_username']}: {(r['content'] or '')[:90]}")
    elif args.cmd == "top-words":
        for word, n in top_words(conn, args.limit, args.author, args.min_len):
            print(f"{n:5d}  {word}")
    elif args.cmd == "emoji":
        for emoji, n in emoji_use(conn, args.limit, args.author):
            print(f"{n:5d}  {emoji}")
