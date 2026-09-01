"""Scrape one Discord DM/group channel's message history into SQLite.

Usage:
    python3 main.py                    # full scrape (resumes automatically)
    python3 main.py --max-batches 3    # quick test run (3 batches of 50)

Layout:
    scraper/api.py        Discord REST client (urllib, 429 handling)
    scraper/config.py     constants, paths, .env loading
    scraper/database.py   schema, resume meta, batch inserts
    scraper/transform.py  API message -> DB row
    output/messages.db    the database (created on first run)
    sql/analysis.sql      starter queries for analysis

Safe to interrupt (Ctrl-C) and re-run at any time: duplicates are impossible
(INSERT OR IGNORE on message id) and the oldest-fetched id is persisted as a
resume point.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from scraper.api import fetch_messages
from scraper.config import (
    REQUEST_DELAY_S,
    Config,
    load_config,
    normalize_batch_size,
)
from scraper.database import get_meta, insert_batch, open_db, set_meta, stats

DISCORD_EPOCH_MS = 1420070400000


class Budget:
    """Limits total API batches per run (used by --max-batches)."""

    def __init__(self, max_batches: int | None):
        self.remaining = max_batches

    def spend(self) -> None:
        if self.remaining is not None:
            self.remaining -= 1

    def reached(self) -> bool:
        return self.remaining is not None and self.remaining <= 0


def _fmt_dur(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def _snowflake_ts(snowflake: str) -> datetime:
    """Discord snowflake IDs encode their creation time in the top bits."""
    return datetime.fromtimestamp(
        ((int(snowflake) >> 22) + DISCORD_EPOCH_MS) / 1000, tz=timezone.utc
    )


def _span_frac(conn, cfg: Config) -> float:
    """Share of the channel's lifetime covered by scraped history:
    (newest - oldest) / (newest - channel creation). A rough proxy — message
    density is uneven, so it is not a % of messages. Capped below 100% until
    the backfill pass actually reaches the first message."""
    lo, hi = conn.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM messages"
    ).fetchone()
    if not lo or not hi:
        return 0.0
    span = (datetime.fromisoformat(hi) - _snowflake_ts(cfg.channel_id)).total_seconds()
    if span <= 0:
        return 0.0
    frac = (datetime.fromisoformat(hi) - datetime.fromisoformat(lo)).total_seconds() / span
    return min(max(frac, 0.0), 0.99)


def _bar(frac: float, width: int = 22) -> str:
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def _progress(fetched: int, start: float, conn) -> str:
    """Discord exposes no total message count, so progress = amount + rate."""
    elapsed = time.monotonic() - start
    rate = fetched / elapsed if elapsed else 0.0
    in_db = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    return f"{_fmt_dur(elapsed)} elapsed | {rate:.1f} msg/s | db: {in_db:,}"


def catch_up(conn, cfg: Config, budget: Budget, start: float) -> int:
    """Newest-first pass. Fresh DB: this is the full scrape. Re-run: grabs
    anything newer than the DB and stops once a whole batch is already stored
    (we've landed inside scraped history)."""
    had_oldest = get_meta(conn, "oldest_id") is not None
    before = None
    fetched = 0

    while True:
        batch = fetch_messages(cfg.token, cfg.channel_id, before, limit=cfg.batch_size)
        if not batch:
            break
        budget.spend()
        inserted = insert_batch(conn, batch)
        fetched += len(batch)
        if not had_oldest:
            set_meta(conn, "oldest_id", batch[-1]["id"])
        print(f"  catch-up: {fetched} fetched, {inserted} new | {_progress(fetched, start, conn)}")
        if inserted == 0 or budget.reached():
            break
        before = batch[-1]["id"]
        time.sleep(REQUEST_DELAY_S)
    return fetched


def backfill(conn, cfg: Config, budget: Budget, start: float) -> int:
    """Continue deeper history from the oldest stored message, updating the
    resume point after every batch, until the API returns an empty batch."""
    oldest = get_meta(conn, "oldest_id")
    fetched = 0

    while True:
        batch = fetch_messages(cfg.token, cfg.channel_id, oldest, limit=cfg.batch_size)
        if not batch:
            break
        budget.spend()
        insert_batch(conn, batch)
        fetched += len(batch)
        oldest = batch[-1]["id"]
        set_meta(conn, "oldest_id", oldest)
        frac = _span_frac(conn, cfg)
        print(
            f"  backfill: {fetched} fetched, oldest now {oldest} | "
            f"{_progress(fetched, start, conn)} | {_bar(frac)} ~{frac:.0%} span"
        )
        if budget.reached():
            break
        time.sleep(REQUEST_DELAY_S)
    return fetched


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape a Discord channel into SQLite.")
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="stop after this many API batches (useful for a quick test run)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="messages per request, 1-100 (default: BATCH_SIZE in .env, else 50)",
    )
    args = parser.parse_args()

    cfg = load_config()
    if args.batch_size is not None:
        cfg.batch_size = normalize_batch_size(args.batch_size)
    conn = open_db()
    budget = Budget(args.max_batches)

    print(f"Scraping channel {cfg.channel_id} into output/messages.db")
    start = time.monotonic()
    try:
        catch_up(conn, cfg, budget, start)
        if not budget.reached():
            backfill(conn, cfg, budget, start)

        total, authors, first, last = stats(conn)
        print("\nDone.")
        print(f"  messages: {total}")
        print(f"  authors:  {authors}")
        print(f"  range:    {first} -> {last}")
        print(f"  took {time.monotonic() - start:.1f}s")
    except (RuntimeError, KeyboardInterrupt) as e:
        print(f"\nStopped: {e}")
        print("Progress is saved — re-run the script to resume.")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
