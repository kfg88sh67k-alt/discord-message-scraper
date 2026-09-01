"""Thin Discord REST client (stdlib urllib only)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from scraper.config import API_BASE, BATCH_SIZE, USER_AGENT


def fetch_messages(token: str, channel_id: str, before: str | None) -> list[dict]:
    """Fetch one batch of messages, newest-first. Empty list = end of history.

    `before` is an exclusive upper bound on message snowflake; pagination walks
    history by feeding back the oldest id of each batch. Retries transparently
    on HTTP 429 using the server's retry_after.
    """
    params = {"limit": str(BATCH_SIZE)}
    if before:
        params["before"] = before
    url = f"{API_BASE}/channels/{channel_id}/messages?{urllib.parse.urlencode(params)}"

    while True:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": token,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = 1.0
                try:
                    retry_after = float(
                        json.loads(e.read().decode()).get("retry_after", 1.0)
                    )
                except Exception:
                    pass
                wait = retry_after + 0.25
                print(f"  rate limited, waiting {wait:.2f}s...")
                time.sleep(wait)
                continue
            if e.code in (401, 403):
                raise RuntimeError("HTTP 401/403: token invalid or channel not accessible")
            if e.code == 404:
                raise RuntimeError(f"HTTP 404: channel {channel_id} not found")
            raise RuntimeError(f"HTTP {e.code} {e.reason}: {url}")
