"""Unified metadata fetcher: Douban / Dangdang / Goodreads / Amazon URLs."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from pagefolio.config import REQUEST_TIMEOUT, USER_AGENT
from pagefolio.sources.dangdang import fetch_product as fetch_dangdang
from pagefolio.sources.douban import fetch_subject as fetch_douban

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)

SOURCE_LABELS = {
    "douban": "豆瓣",
    "dangdang": "当当",
    "goodreads": "Goodreads",
    "amazon": "Amazon",
}


def detect_source(url: str) -> str:
    u = url.strip().lower()
    if "douban.com" in u:
        return "douban"
    if "dangdang.com" in u:
        return "dangdang"
    if "goodreads.com" in u:
        return "goodreads"
    if re.search(r"amazon\.(com|cn|co\.uk|de|fr|jp)", u):
        return "amazon"
    raise ValueError("不支持的链接。请使用豆瓣或当当的书籍页面链接。")


def _normalize(info: dict, source: str, source_url: str) -> dict:
    return {
        "source": source,
        "source_label": SOURCE_LABELS[source],
        "source_url": source_url,
        "title": info.get("title") or "",
        "subtitle": info.get("subtitle"),
        "author": info.get("author"),
        "translator": info.get("translator"),
        "isbn": info.get("isbn"),
        "asin": info.get("asin"),
        "publisher": info.get("publisher"),
        "cover_url": info.get("cover_url"),
    }


def fetch_from_url(url: str) -> dict:
    source = detect_source(url)
    if source == "douban":
        raw = fetch_douban(url)
        return _normalize(
            {
                "title": raw["title"],
                "subtitle": raw.get("subtitle"),
                "author": raw.get("author"),
                "translator": raw.get("translator"),
                "isbn": raw.get("isbn"),
                "publisher": raw.get("publisher"),
                "cover_url": raw.get("cover_url"),
            },
            source,
            raw.get("douban_url") or url,
        )
    if source == "dangdang":
        raw = fetch_dangdang(url)
        return _normalize(
            {
                "title": raw["title"],
                "subtitle": raw.get("subtitle"),
                "author": raw.get("author"),
                "translator": raw.get("translator"),
                "isbn": raw.get("isbn"),
                "publisher": raw.get("publisher"),
                "cover_url": raw.get("cover_url"),
            },
            source,
            raw.get("dangdang_url") or url,
        )
    if source == "goodreads":
        return _fetch_goodreads(url)
    return _fetch_amazon(url)


def _fetch_page(url: str, referer: str | None = None) -> BeautifulSoup:
    resp = session.get(url, timeout=REQUEST_TIMEOUT, headers={"Referer": referer or url})
    if resp.status_code != 200:
        raise ValueError(f"无法访问页面（HTTP {resp.status_code}）")
    return BeautifulSoup(resp.text, "lxml")


def _extract_amazon_asin(url: str) -> str | None:
    match = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", url, re.I)
    return match.group(1).upper() if match else None


def _fetch_amazon(url: str) -> dict:
    asin = _extract_amazon_asin(url)
    page_url = url.strip()
    if asin and "/dp/" not in page_url.lower():
        host_match = re.search(r"https?://[^/]+", page_url)
        host = host_match.group(0) if host_match else "https://www.amazon.com"
        page_url = f"{host}/dp/{asin}"

    soup = _fetch_page(page_url)
    title_el = soup.select_one("#productTitle") or soup.select_one("span#ebooksProductTitle")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        raise ValueError("未能解析书名")

    author_el = (
        soup.select_one("#bylineInfo .author a")
        or soup.select_one("a.contributorNameID")
        or soup.select_one("#bylineInfo a")
    )
    cover_el = (
        soup.select_one("#imgTagWrapperId img")
        or soup.select_one("#landingImage")
        or soup.select_one("img[data-image-latency='s-product-image']")
    )
    cover_url = None
    if cover_el:
        cover_url = cover_el.get("data-old-hires") or cover_el.get("src") or cover_el.get("data-src")

    if not asin:
        asin_el = soup.select_one("input#ASIN")
        asin = asin_el.get("value") if asin_el else _extract_amazon_asin(page_url)

    return _normalize(
        {
            "title": title,
            "author": author_el.get_text(strip=True) if author_el else None,
            "asin": asin,
            "cover_url": cover_url,
        },
        "amazon",
        page_url,
    )


def _fetch_goodreads(url: str) -> dict:
    book_id = re.search(r"goodreads\.com/book/show/(\d+)", url, re.I)
    page_url = f"https://www.goodreads.com/book/show/{book_id.group(1)}" if book_id else url.strip()

    soup = _fetch_page(page_url, referer="https://www.goodreads.com/")
    title_el = (
        soup.select_one("h1[data-testid='bookTitle']")
        or soup.select_one("h1#bookTitle")
        or soup.select_one("h1.bookTitle")
    )
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        raise ValueError("未能解析书名")

    author_el = (
        soup.select_one("span[data-testid='name']")
        or soup.select_one("a.authorName")
        or soup.select_one("span.ContributorLink__name")
    )
    cover_el = (
        soup.select_one("img.ResponsiveImage")
        or soup.select_one("#coverImage")
        or soup.select_one("img.bookCover")
    )
    cover_url = None
    if cover_el:
        cover_url = cover_el.get("src") or cover_el.get("data-src")
        if cover_url:
            cover_url = re.sub(r"\._[A-Z0-9]+_\.", ".", cover_url)

    isbn = None
    details = soup.select_one("#details") or soup.select_one('[data-testid="bookDetails"]')
    if details:
        isbn_match = re.search(
            r"ISBN(?:-1[03])?:?\s*([\dXx-]{10,17})",
            details.get_text(" ", strip=True),
        )
        if isbn_match:
            isbn = isbn_match.group(1).replace("-", "")

    return _normalize(
        {
            "title": title,
            "author": author_el.get_text(strip=True) if author_el else None,
            "isbn": isbn,
            "cover_url": cover_url,
        },
        "goodreads",
        page_url,
    )
