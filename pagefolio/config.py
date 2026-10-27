"""Paths and runtime constants."""

import os
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
# 请求超时采用 (connect_timeout, read_timeout) 二元组：
#   connect_timeout  TCP 建立连接阶段超时（8s 足够，避免卡在 SYN 重试）
#   read_timeout     首字节 / 响应体读取超时（30s 比原来 20s 更抗抖，但仍有限）
REQUEST_TIMEOUT_CONNECT = 8
REQUEST_TIMEOUT_READ = 30
REQUEST_TIMEOUT = (REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ)
# 指数退避重试：仅对网络层异常（Timeout / ConnectionError / 5xx）生效
#   重试次数     3 次（首次 + 2 次重试，总尝试 = 3）
#   基础延时     1.5s，延时序列 1.5s → 3.0s → 6.0s（在豆瓣限速时避免快速重试被封禁）
REQUEST_MAX_RETRIES = 3
REQUEST_RETRY_BASE_DELAY = 1.5
SCRAPE_DELAY_SEC = 1.2

# Optional: paste your logged-in Douban cookies into a local, git-ignored file
# to bypass the 403 anti-crawl wall.
#
# Chrome → book.douban.com (log in first) → F12 → Network → refresh → click
# any book.douban.com request → Headers → "Cookie:" → copy the *entire* value.
# Then either:
#   export PAGEFOLIO_DOUBAN_COOKIE='paste here'
# OR save the raw value (single line, no quotes) into:
#   pagefolio/douban_cookie.txt
#
# Priority: environment variable > local file. The local file is git-ignored.
LOCAL_COOKIE_FILE = Path(__file__).resolve().parent / "douban_cookie.txt"


def _load_douban_cookie() -> str:
    env = os.environ.get("PAGEFOLIO_DOUBAN_COOKIE", "").strip()
    if env:
        return env
    try:
        return LOCAL_COOKIE_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


DOUBAN_COOKIE = _load_douban_cookie()
