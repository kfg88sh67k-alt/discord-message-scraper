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

from scraper.api import fetch_messages
from scraper.config import REQUEST_DELAY_S, Config, load_config
from scraper.database import get_meta, insert_batch, open_db, set_meta, stats


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
        batch = fetch_messages(cfg.token, cfg.channel_id, before)
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
        batch = fetch_messages(cfg.token, cfg.channel_id, oldest)
        if not batch:
            break
        budget.spend()
        insert_batch(conn, batch)
        fetched += len(batch)
        oldest = batch[-1]["id"]
        set_meta(conn, "oldest_id", oldest)
        print(f"  backfill: {fetched} fetched, oldest now {oldest} | {_progress(fetched, start, conn)}")
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
    args = parser.parse_args()

    cfg = load_config()
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
