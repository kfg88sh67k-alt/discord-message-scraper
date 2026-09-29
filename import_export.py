"""Import channels from Discord's official data export ("Request Data")
into the same SQLite schema the scraper (main.py) produces, so the
existing analysis toolkit (analysis.py / python3 -m analysis) works on it
unchanged.

Get the export from Discord: Settings -> Privacy & Safety -> Request Data.
You'll receive a "package.zip" (or an already-unzipped folder) containing:

    messages/
      index.json          maps channel id -> channel name
      c<channel_id>/
        channel.json       channel metadata (type, recipients, guild, ...)
        messages.csv        this channel's messages

Usage:
    python3 import_export.py path/to/package.zip
    python3 import_export.py path/to/package.zip --channel-id 123 --channel-id 456
    python3 import_export.py path/to/unzipped_dir --channel-id 123

Each channel is written to its own database: output/<channel_id>.db
(matching `main.py --channel-id <id>`), so a channel already scraped via the
API can be merged with (INSERT OR IGNORE, by message id) or cross-checked
against its export.

Caveat: the export's messages.csv has no reliable per-message author column
in most export versions -- it's just ID, Timestamp, Contents, Attachments.
Author is therefore taken from `channel.json`'s recipients when the channel
has exactly one other participant (a 1:1 DM); otherwise it's left NULL and
you'll see it as blank in `author_username`. The `raw` column stores the
csv row as JSON either way, so nothing is lost.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from scraper.config import OUTPUT_DIR
from scraper.database import insert_batch, open_db, stats

CHANNEL_DIR_RE = re.compile(r"^c(\d+)$")


def _find_messages_root(root: Path) -> Path:
    """Locate the messages/ directory inside an export, however it's laid out."""
    candidates = [root / "messages", root]
    for c in candidates:
        if (c / "index.json").exists() or any(CHANNEL_DIR_RE.match(p.name) for p in c.iterdir() if p.is_dir()):
            return c
    found = list(root.rglob("index.json"))
    if found:
        return found[0].parent
    raise SystemExit(f"Couldn't find a messages/ folder (with index.json) under {root}")


def _load_channel_meta(chan_dir: Path) -> dict:
    meta_path = chan_dir / "channel.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _single_recipient(meta: dict) -> dict | None:
    """For a 1:1 DM, channel.json lists exactly one other recipient -- the
    export owner's own messages have no separate marker, so this is a
    best-effort guess, not ground truth."""
    recipients = meta.get("recipients") or []
    if len(recipients) == 1:
        return recipients[0]
    return None


def _row_from_csv(record: dict, channel_id: str, fallback_author: dict | None) -> dict:
    msg_id = record.get("ID") or record.get("Id") or record.get("id")
    timestamp = record.get("Timestamp") or record.get("timestamp")
    contents = record.get("Contents") or record.get("contents") or ""
    attachments = record.get("Attachments") or record.get("attachments") or ""

    author_id = record.get("AuthorID") or record.get("Author ID") or (
        fallback_author.get("id") if fallback_author else None
    ) or "unknown"
    author_username = record.get("Author") or record.get("AuthorName") or (
        fallback_author.get("username") if fallback_author else None
    )

    return {
        "id": msg_id,
        "channel_id": channel_id,
        "author": {"id": author_id, "username": author_username},
        "content": contents,
        "timestamp": timestamp,
        "edited_timestamp": None,
        "attachments": [{"url": u} for u in attachments.split(" ") if u],
        "type": None,
        "pinned": False,
        # keep the raw export row too, alongside the reconstructed shape
        "_export_row": record,
    }


def import_channel(chan_dir: Path, channel_id: str) -> int:
    meta = _load_channel_meta(chan_dir)
    fallback_author = _single_recipient(meta)
    csv_path = chan_dir / "messages.csv"
    if not csv_path.exists():
        print(f"  skip {channel_id}: no messages.csv in {chan_dir}")
        return 0

    db_path = OUTPUT_DIR / f"{channel_id}.db"
    conn = open_db(db_path)

    batch = []
    total_inserted = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for record in csv.DictReader(f):
            row = _row_from_csv(record, channel_id, fallback_author)
            if not row["id"] or not row["timestamp"]:
                continue
            batch.append(row)
            if len(batch) >= 500:
                total_inserted += insert_batch(conn, batch)
                batch.clear()
    if batch:
        total_inserted += insert_batch(conn, batch)

    total, authors, first, last = stats(conn)
    conn.close()
    print(
        f"  {channel_id} -> {db_path}: {total_inserted} new rows "
        f"(db now has {total} messages, {authors} authors, {first} .. {last})"
    )
    return total_inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import channel(s) from a Discord data-export package into per-channel SQLite databases."
    )
    parser.add_argument("path", help="path to package.zip, or an already-unzipped export folder")
    parser.add_argument(
        "--channel-id",
        action="append",
        dest="channel_ids",
        default=None,
        help="only import this channel id (repeatable); default: import every channel in the export",
    )
    args = parser.parse_args()

    src = Path(args.path)
    if not src.exists():
        raise SystemExit(f"No such path: {src}")

    with tempfile.TemporaryDirectory(prefix="discord-export-") as tmp:
        if src.is_file() and zipfile.is_zipfile(src):
            print(f"Extracting {src} ...")
            with zipfile.ZipFile(src) as zf:
                zf.extractall(tmp)
            root = Path(tmp)
        else:
            root = src

        messages_root = _find_messages_root(root)
        wanted = set(args.channel_ids) if args.channel_ids else None

        chan_dirs = sorted(
            p for p in messages_root.iterdir() if p.is_dir() and CHANNEL_DIR_RE.match(p.name)
        )
        if wanted:
            chan_dirs = [p for p in chan_dirs if CHANNEL_DIR_RE.match(p.name).group(1) in wanted]
            missing = wanted - {CHANNEL_DIR_RE.match(p.name).group(1) for p in chan_dirs}
            for m in missing:
                print(f"  warning: channel {m} not found in this export")

        if not chan_dirs:
            raise SystemExit("No matching channels found in the export.")

        print(f"Importing {len(chan_dirs)} channel(s) from {src}")
        for chan_dir in chan_dirs:
            channel_id = CHANNEL_DIR_RE.match(chan_dir.name).group(1)
            import_channel(chan_dir, channel_id)


if __name__ == "__main__":
    main()
