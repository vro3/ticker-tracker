import json
import os
from pathlib import Path

APP_HOME = Path(os.environ.get("TICKER_TRACKER_HOME", Path.home() / "TickerTracker"))
CONFIG_PATH = APP_HOME / "config.json"
DB_PATH = APP_HOME / "tracker.db"
SCREENSHOT_DIR = APP_HOME / "screenshots"
LOG_PATH = APP_HOME / "tracker.log"

DEFAULTS = {
    # Web dashboard port. Open http://<mini-name>.local:8787 from any device on the network.
    "port": 8787,
    # How often to look for new iMessages (seconds).
    "poll_seconds": 30,
    # How often to refresh prices (minutes).
    "price_refresh_minutes": 15,
    # Vision backend: "auto" (API key if present, else Claude Code CLI), "api", or "cli".
    "vision_backend": "auto",
    "anthropic_api_key": "",
    "model": "claude-opus-5",
    # Map iMessage handles (phone numbers / emails) to display names.
    # Example: {"+16155551234": "Vince", "friend@icloud.com": "Dana"}
    "people": {},
    # Only process chats whose display name or identifier contains this text. Empty = all chats.
    "chat_filter": "",
    # Time zone used for display and for deciding "day sent".
    "timezone": "America/Chicago",
    # Path to the Messages database on this Mac.
    "chat_db": str(Path.home() / "Library/Messages/chat.db"),
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    return cfg


def ensure_dirs():
    APP_HOME.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULTS, f, indent=2)


def api_key(cfg: dict) -> str:
    return cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
