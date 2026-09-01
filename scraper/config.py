"""Configuration: constants, paths, and .env loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

API_BASE = "https://discord.com/api/v9"
BATCH_SIZE = 50
BATCH_SIZE_MAX = 100  # Discord's hard per-request limit
REQUEST_DELAY_S = 0.8
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_DIR / ".env"
OUTPUT_DIR = PROJECT_DIR / "output"
DB_PATH = OUTPUT_DIR / "messages.db"


@dataclass
class Config:
    token: str
    channel_id: str
    batch_size: int


def normalize_batch_size(value) -> int:
    """Validate the per-request message count (Discord caps at 100)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise SystemExit(f"Invalid BATCH_SIZE: {value!r} — must be an integer")
    if not 1 <= n <= BATCH_SIZE_MAX:
        raise SystemExit(
            f"BATCH_SIZE must be 1-{BATCH_SIZE_MAX} (Discord's API maximum is {BATCH_SIZE_MAX})"
        )
    return n


def load_config() -> Config:
    env = _load_env_file()
    token = env.get("DISCORD_TOKEN")
    channel_id = env.get("CHANNEL_ID")
    if not token or not channel_id:
        raise SystemExit(
            "Missing DISCORD_TOKEN or CHANNEL_ID. Copy .env.example to .env and fill them in."
        )
    batch_size = normalize_batch_size(env.get("BATCH_SIZE", BATCH_SIZE))
    return Config(token=token, channel_id=channel_id, batch_size=batch_size)


def _load_env_file() -> dict:
    """Minimal .env loader; real environment variables take precedence."""
    env = dict(os.environ)
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip())
    return env
