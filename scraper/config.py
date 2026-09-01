"""Configuration: constants, paths, and .env loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

API_BASE = "https://discord.com/api/v9"
BATCH_SIZE = 50
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


def load_config() -> Config:
    env = _load_env_file()
    token = env.get("DISCORD_TOKEN")
    channel_id = env.get("CHANNEL_ID")
    if not token or not channel_id:
        raise SystemExit(
            "Missing DISCORD_TOKEN or CHANNEL_ID. Copy .env.example to .env and fill them in."
        )
    return Config(token=token, channel_id=channel_id)


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
