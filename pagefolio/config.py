"""Paths and runtime constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DB_PATH = ROOT / "reading.db"
COVER_DIR = ROOT / "cover"

HOST = "127.0.0.1"
PORT = 8765

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
SCRAPE_DELAY_SEC = 1.2
