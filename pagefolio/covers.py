"""Batch cover scraping (CLI). Source order: Dangdang → Douban → Goodreads."""

from __future__ import annotations

import argparse
import re
import sqlite3
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from pagefolio.config import (
    COVER_DIR,
    DB_PATH,
    DOUBAN_COOKIE,
    REQUEST_TIMEOUT,
    SCRAPE_DELAY_SEC,
    USER_AGENT,
)
from pagefolio.db import connect


def _inject_douban_cookies(session: requests.Session) -> None:
    """Apply logged-in Douban cookies (if configured) to cover scraping too."""
    if not DOUBAN_COOKIE:
        return
    for chunk in DOUBAN_COOKIE.split(";"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k, v = k.strip(), v.strip()
        if not k:
            continue
        session.cookies.set(k, v, domain=".douban.com")


session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://book.douban.com/",
    }
)
_inject_douban_cookies(session)


def cover_filename(book_id: int) -> str:
    return f"{book_id:04d}.jpg"


def cover_relpath(book_id: int) -> str:
    return f"cover/{cover_filename(book_id)}"


def sleep() -> None:
    time.sleep(SCRAPE_DELAY_SEC)


def download_image(url: str, dest) -> bool:
    if not url or url.startswith("data:"):
        return False
    if url.startswith("//"):
        url = "https:" + url
    url = re.sub(r"/s\d+x\d+/", "/l/", url)
    url = url.replace("/view/subject/s/", "/view/subject/l/")

    sleep()
    headers = {}
    if "doubanio.com" in url:
        headers["Referer"] = "https://book.douban.com/"
    if "ddimg.cn" in url or "dangdang.com" in url:
        headers["Referer"] = "https://www.dangdang.com/"
    resp = session.get(url, timeout=REQUEST_TIMEOUT, stream=True, headers=headers)
    if resp.status_code != 200:
        return False
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "image" not in ctype and not url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return False
    data = resp.content
    if len(data) < 1024:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def download_cover_for_book(url: str, book_id: int) -> str:
    dest = COVER_DIR / cover_filename(book_id)
    if not download_image(url, dest):
        raise ValueError("封面图片下载失败")
    return cover_relpath(book_id)


def _search_query(book: sqlite3.Row) -> str:
    parts = [book["title"] or "", book["subtitle"] or "", book["author"] or ""]
    return " ".join(p for p in parts if p).strip()


def _cover_from_douban(book: sqlite3.Row) -> str | None:
    queries = [q for q in [book["isbn"], _search_query(book), book["title"]] if q]
    for q in queries:
        sleep()
        url = "https://book.douban.com/j/subject_suggest?q=" + urllib.parse.quote(q)
        try:
            resp = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"Referer": "https://book.douban.com/", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                continue
            items = resp.json()
        except (requests.RequestException, ValueError):
            continue
        if not isinstance(items, list) or not items:
            continue
        pic = items[0].get("pic") or items[0].get("img")
        if pic:
            return pic.replace("/s/", "/l/") if "/s/" in pic else pic
    return None


def _cover_from_dangdang(book: sqlite3.Row) -> str | None:
    queries = [q for q in [_search_query(book), book["title"]] if q]
    for q in queries:
        sleep()
        url = "https://search.dangdang.com/?key=" + urllib.parse.quote(q) + "&act=input"
        try:
            resp = session.get(
                url,
                timeout=REQUEST_TIMEOUT,
                headers={"Referer": "https://www.dangdang.com/"},
            )
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            ul = soup.select_one("ul.bigimg")
            if ul:
                first_li = ul.select_one("li")
                if first_li:
                    img = first_li.select_one("img")
                    if img:
                        src = img.get("src") or img.get("data-original")
                        if src and ("ddimg" in src or "img" in src):
                            if src.startswith("//"):
                                src = "https:" + src
                            return src
            # fallback: any ddimg image with non-empty alt
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-original") or ""
                alt = (img.get("alt") or "").strip()
                if ("ddimg" in src or "ddimg.cn" in src) and len(alt) > 2:
                    if src.startswith("//"):
                        src = "https:" + src
                    return src
        except requests.RequestException:
            continue
    return None


def _cover_from_goodreads(book: sqlite3.Row) -> str | None:
    sleep()
    url = "https://www.goodreads.com/search?q=" + urllib.parse.quote(_search_query(book))
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    img = soup.select_one("table.tableList img.bookCover") or soup.select_one("img.bookCover")
    if not img:
        return None
    src = img.get("src") or img.get("data-src")
    return re.sub(r"\._[A-Z0-9]+_\.", ".", src) if src else None


SOURCES = (
    ("dangdang", _cover_from_dangdang),
    ("douban", _cover_from_douban),
    ("goodreads", _cover_from_goodreads),
)


def query_books(
    conn: sqlite3.Connection,
    *,
    book_id: int | None,
    year: int | None,
    force: bool,
) -> list[sqlite3.Row]:
    sql = "SELECT DISTINCT b.id, b.title, b.subtitle, b.author, b.translator, b.isbn, b.asin, b.local_cover_path FROM books b"
    params: list[object] = []
    where: list[str] = []
    if year is not None:
        sql += " JOIN reading_months rm ON rm.book_id = b.id"
        where.append("rm.year = ?")
        params.append(year)
    if book_id is not None:
        where.append("b.id = ?")
        params.append(book_id)
    if not force:
        where.append("(b.local_cover_path IS NULL OR b.local_cover_path = '')")
    if where:
        sql += " WHERE " + " AND ".join(where)
    return list(conn.execute(sql + " ORDER BY b.id", params))


def scrape_one(conn: sqlite3.Connection, book: sqlite3.Row, force: bool) -> str:
    dest = COVER_DIR / cover_filename(book["id"])
    rel = cover_relpath(book["id"])
    if dest.exists() and not force and book["local_cover_path"]:
        return f"skip (exists) {rel}"

    last_err = "no source matched"
    for name, fetcher in SOURCES:
        try:
            cover_url = fetcher(book)
        except Exception as exc:  # noqa: BLE001
            last_err = f"{name}: {exc}"
            continue
        if not cover_url:
            last_err = f"{name}: empty"
            continue
        if not download_image(cover_url, dest):
            last_err = f"{name}: bad image"
            continue
        conn.execute(
            "UPDATE books SET cover_url = ?, local_cover_path = ?, "
            "updated_at = datetime('now') WHERE id = ?",
            (cover_url, rel, book["id"]),
        )
        conn.commit()
        return f"ok via {name} → {rel}"
    return f"fail — {last_err}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape covers for books in reading.db")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--id", type=int, dest="book_id")
    parser.add_argument("--year", type=int)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Missing {DB_PATH}; run: python run.py init")

    COVER_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    books = query_books(conn, book_id=args.book_id, year=args.year, force=args.force)
    if args.limit is not None:
        books = books[: args.limit]
    if not books:
        print("Nothing to scrape.")
        return

    ok = fail = skip = 0
    for book in books:
        result = scrape_one(conn, book, force=args.force)
        print(f"[{book['id']}] {book['title']}: {result}")
        ok += result.startswith("ok")
        skip += result.startswith("skip")
        fail += result.startswith("fail")
    conn.close()
    print(f"\nDone. ok={ok} skip={skip} fail={fail} total={len(books)}")


if __name__ == "__main__":
    main()
