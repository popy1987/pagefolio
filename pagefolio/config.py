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

# Optional: paste your logged-in Douban cookies here (or export env var before
# running the server / CLI) to bypass the 403 anti-crawl wall.
#
# Chrome → book.douban.com (log in first) → F12 → Network → refresh → click
# any book.douban.com request → Headers → "Cookie:" → copy the *entire* value.
# Then either:
#   export PAGEFOLIO_DOUBAN_COOKIE='paste here'
# OR paste directly into the string below:
DOUBAN_COOKIE = (
    os.environ.get("PAGEFOLIO_DOUBAN_COOKIE", "").strip()
    or """_ga=GA1.1.1353306152.1657631001; _vwo_uuid_v2=D99CEFFD7D51EE31A327C67129FA5429B|57a4ba40309acd1acf7635c84433e711; __utmc=81379588; _pk_id.100001.3ac3=f6958a2cb80e968f.1761474470.; ll="118124"; viewed="37531200_37451436"; push_doumail_num=0; __utmc=30149280; __utmv=30149280.7278; _ga_RXNMP372GL=GS2.1.s1777990453$o33$g0$t1777990460$j53$l0$h0; bid=xqAJy3OZRuk; frodotk_db="bbfefff723b0bdaf33fcffe56b12390d"; ct=y; push_noty_num=0; dbcl2="72785266:nsgSNVqqI4g"; ck=LHiA; __utma=30149280.1353306152.1657631001.1787750121.1787753140.124; __utmz=30149280.1787753140.124.26.utmcsr=douban.com|utmccn=(referral)|utmcmd=referral|utmcct=/people/noseafood/; __utma=81379588.1878140645.1659189515.1787235660.1787753140.605; __utmz=81379588.1787753140.605.495.utmcsr=douban.com|utmccn=(referral)|utmcmd=referral|utmcct=/people/noseafood/; _pk_ref.100001.3ac3=%5B%22%22%2C%22%22%2C1787753141%2C%22https%3A%2F%2Fwww.douban.com%2Fpeople%2Fnoseafood%2F%3F_i%3D7665550xqAJy3O%2C7750120xqAJy3O%22%5D; _pk_ses.100001.3ac3=1; __utmt_douban=1; __utmb=30149280.6.10.1787753140; __utmt=1; __utmb=81379588.6.10.1787753140"""
)
