"""Douban book subject page parser."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from pagefolio.config import REQUEST_TIMEOUT, USER_AGENT

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)


def extract_subject_id(url: str) -> str | None:
    match = re.search(r"book\.douban\.com/subject/(\d+)", url.strip())
    return match.group(1) if match else None


def normalize_douban_url(url: str) -> str:
    subject_id = extract_subject_id(url)
    if not subject_id:
        raise ValueError("无效的豆瓣读书链接，需形如 https://book.douban.com/subject/12345/")
    return f"https://book.douban.com/subject/{subject_id}/"


def _info_value(info_text: str, label: str) -> str | None:
    pattern = rf"{re.escape(label)}:\s*(.+?)(?:\n|$)"
    match = re.search(pattern, info_text)
    return match.group(1).strip() if match else None


def fetch_subject(url: str) -> dict:
    page_url = normalize_douban_url(url)
    resp = session.get(page_url, timeout=REQUEST_TIMEOUT, headers={"Referer": page_url})
    if resp.status_code != 200:
        raise ValueError(f"无法访问豆瓣页面（HTTP {resp.status_code}）")

    soup = BeautifulSoup(resp.text, "lxml")
    h1 = soup.select_one("h1")
    title = ""
    subtitle = None
    if h1:
        reviewed = h1.select_one("span[property='v:itemreviewed']")
        if reviewed:
            title = reviewed.get_text(strip=True)
            extra = h1.get_text(strip=True).replace(title, "", 1).strip(" /：:")
            subtitle = extra or None
        else:
            parts = [s.get_text(strip=True) for s in h1.select("span") if s.get_text(strip=True)]
            if parts:
                title = parts[0]
                subtitle = " / ".join(parts[1:]) if len(parts) > 1 else None
            else:
                title = h1.get_text(strip=True)
    if not title:
        raise ValueError("未能解析书名")

    cover_el = soup.select_one("#mainpic img") or soup.select_one(".nbg img")
    cover_url = None
    if cover_el:
        cover_url = cover_el.get("src") or cover_el.get("data-src")
        if cover_url:
            cover_url = cover_url.replace("/s/", "/l/")

    author_els = soup.select("#info a[href*='/author/'], #info a[href*='/search/'][href*='author']")
    author = "、".join(dict.fromkeys(el.get_text(strip=True) for el in author_els)) or None

    info = soup.select_one("#info")
    info_text = info.get_text("\n", strip=True) if info else ""
    translator = _info_value(info_text, "译者")

    return {
        "douban_id": extract_subject_id(page_url),
        "douban_url": page_url,
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "translator": translator,
        "isbn": _info_value(info_text, "ISBN"),
        "publisher": _info_value(info_text, "出版社"),
        "cover_url": cover_url,
    }
