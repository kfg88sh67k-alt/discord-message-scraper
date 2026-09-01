"""Report generation: text dump + charts into output/report/."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .db import REAL_MESSAGES, connect
from scraper.config import OUTPUT_DIR

WORD_RE = re.compile(r"[a-zA-Z']+")
BUCKET_FMTS = {"year": "%Y", "month": "%Y-%m", "day": "%Y-%m-%d"}


def _bucket_fmt(conn) -> tuple[str, str]:
    """Pick time-bucket granularity from the data's actual span."""
    from datetime import datetime

    lo, hi = conn.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM messages"
    ).fetchone()
    span_days = max(((datetime.fromisoformat(hi) - datetime.fromisoformat(lo)).days), 1)
    if span_days > 730:
        return "%Y", "year"
    if span_days > 60:
        return "%Y-%m", "month"
    return "%Y-%m-%d", "day"


def report(out_dir=None, bucket: str = "year") -> Path:
    """Generate word-count AND message-count charts (pie + timeline each) plus
    a text dump of the exact data behind them into output/report/.

    bucket: "year" (default), "month", "day", or "auto" (pick from data span).
    """
    out_dir = Path(out_dir) if out_dir else OUTPUT_DIR / "report"
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()

    if bucket == "auto":
        fmt, unit = _bucket_fmt(conn)
    else:
        fmt, unit = BUCKET_FMTS[bucket], bucket
    rows = conn.execute(
        f"SELECT strftime('{fmt}', created_at) AS bucket, author_username, content "
        f"FROM messages WHERE {REAL_MESSAGES} ORDER BY created_at"
    ).fetchall()

    # metric = "words" or "messages"; counters keyed accordingly
    user_totals = {"words": Counter(), "messages": Counter()}
    bucket_user = {"words": Counter(), "messages": Counter()}   # (bucket, user) -> n
    bucket_totals = {"words": Counter(), "messages": Counter()}
    for r in rows:
        user = r["author_username"] or "?"
        n_words = len(WORD_RE.findall(r["content"] or ""))
        user_totals["words"][user] += n_words
        user_totals["messages"][user] += 1
        bucket_user["words"][(r["bucket"], user)] += n_words
        bucket_user["messages"][(r["bucket"], user)] += 1
        bucket_totals["words"][r["bucket"]] += n_words
        bucket_totals["messages"][r["bucket"]] += 1

    # one canonical user order (by words) so colors match across all charts
    users = [u for u, _ in user_totals["words"].most_common()]
    buckets = sorted(bucket_totals["words"])

    # --- text dump: the raw numbers behind every chart ---
    lines = [
        "DISCORD ACTIVITY REPORT",
        "=" * 60,
        f"messages: {sum(user_totals['messages'].values())}  "
        f"words: {sum(user_totals['words'].values())}  "
        f"users: {len(users)}  bucket: {unit}",
        f"span: {buckets[0]} -> {buckets[-1]}",
    ]
    for metric, label in (("words", "WORDS"), ("messages", "MESSAGES")):
        total = sum(user_totals[metric].values())
        lines += [
            "",
            f"{label} PER USER (pie chart data)",
            "-" * 60,
            f"{'user':<20} {label.lower():>9} {'share':>7}",
        ]
        for u in users:
            pct = 100 * user_totals[metric][u] / total if total else 0
            lines.append(f"{u:<20} {user_totals[metric][u]:>9} {pct:>6.1f}%")
        lines += [
            "",
            f"{label} OVER TIME (line chart data, per {unit})",
            "-" * 60,
            f"{'bucket':<12} {'total':>6} " + " ".join(f"{u[:10]:>10}" for u in users),
        ]
        for b in buckets:
            cells = " ".join(f"{bucket_user[metric].get((b, u), 0):>10}" for u in users)
            lines.append(f"{b:<12} {bucket_totals[metric][b]:>6} {cells}")
    text = "\n".join(lines)
    (out_dir / "report.txt").write_text(text + "\n")
    print(text)
    print(f"\ntext report: {out_dir / 'report.txt'}")

    # --- charts ---
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("pip install matplotlib to also get the charts")
        return out_dir

    def _pie(metric: str, fname: str) -> None:
        total = sum(user_totals[metric].values())
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(
            [user_totals[metric][u] for u in users],
            labels=users,
            autopct="%1.1f%%",
            colors=plt.cm.tab20.colors,
        )
        ax.set_title(f"{metric.capitalize()} share by user (total {total:,})")
        fig.tight_layout()
        fig.savefig(out_dir / fname, dpi=150)
        plt.close(fig)

    def _line(metric: str, fname: str) -> None:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(buckets, [bucket_totals[metric][b] for b in buckets], color="black",
                linewidth=3, label="TOTAL", zorder=10)
        for i, u in enumerate(users):
            ax.plot(
                buckets,
                [bucket_user[metric].get((b, u), 0) for b in buckets],
                marker="o",
                color=plt.cm.tab20.colors[i % 20],
                label=u,
            )
        ax.set_title(f"{metric.capitalize()} over time (per {unit})")
        ax.set_ylabel(metric)
        ax.legend()
        ax.grid(alpha=0.3)
        fig.autofmt_xdate(rotation=45)
        fig.tight_layout()
        fig.savefig(out_dir / fname, dpi=150)
        plt.close(fig)

    _pie("words", "words_pie.png")
    _line("words", "words_over_time.png")
    _pie("messages", "messages_pie.png")
    _line("messages", "messages_over_time.png")

    print(f"charts:     {out_dir / 'words_pie.png'}")
    print(f"            {out_dir / 'words_over_time.png'}")
    print(f"            {out_dir / 'messages_pie.png'}")
    print(f"            {out_dir / 'messages_over_time.png'}")
    return out_dir
