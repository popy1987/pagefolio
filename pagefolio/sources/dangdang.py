"""Dangdang (当当网 product.dangdang.com) book product page parser."""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

from pagefolio.config import (
    REQUEST_MAX_RETRIES,
    REQUEST_RETRY_BASE_DELAY,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

session = requests.Session()
session.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
)

_PRODUCT_ID_RE = re.compile(r"product\.dangdang\.com/(\d+)\.html", re.I)


def fetch_with_retry(
    sess: requests.Session,
    url: str,
    *,
    method: str = "GET",
    timeout=REQUEST_TIMEOUT,
    max_retries: int = REQUEST_MAX_RETRIES,
    base_delay: float = REQUEST_RETRY_BASE_DELAY,
    accept_status=(200,),
    headers: dict | None = None,
    **kwargs,
) -> requests.Response | None:
    """与 covers.fetch_with_retry 语义一致的封装：二元 timeout + 指数退避。"""
    last_resp: requests.Response | None = None
    for attempt in range(max_retries):
        try:
            resp = sess.request(method, url, timeout=timeout, headers=headers, **kwargs)
            if resp.status_code in accept_status:
                return resp
            if 500 <= resp.status_code < 600:
                last_resp = resp
            else:
                return resp
        except (requests.Timeout, requests.ConnectionError, requests.ChunkedEncodingError):
            pass
        except requests.RequestException:
            return None
        if attempt < max_retries - 1:
            time.sleep(base_delay * (2 ** attempt))
    return last_resp


def extract_product_id(url: str) -> str | None:
    match = _PRODUCT_ID_RE.search(url.strip())
    return match.group(1) if match else None


def normalize_dangdang_url(url: str) -> str:
    pid = extract_product_id(url)
    if not pid:
        raise ValueError("无效的当当商品链接，需形如 https://product.dangdang.com/1234567890.html")
    return f"https://product.dangdang.com/{pid}.html"


def _messbox_kv(info_text: str, label: str) -> str | None:
    """Dangdang's messbox separates key: value with line breaks and noise.

    The text looks like:
        作者:[美]\n布莱克J.哈里斯\n出版社:\n新星出版社\n出版时间:2023年08月\n1\n条评论
    So we split on newlines, find the line ending with 'label:', and concatenate
    non-empty following lines until the next known-key line or a numeric/noise line.
    """
    lines = [ln.strip() for ln in re.split(r"[\n\r]+", info_text) if ln.strip()]
    stop_keys = {"作者:", "译者:", "出版社:", "出版时间:", "开　　本:", "开本:", "纸　　张:", "纸张:",
                 "包　　装:", "包装:", "是否套装:", "丛书名:", "ISBN:", "国际标准书号ISBN:",
                 "所属分类:", "页　　数:", "页数:", "字　　数:", "字数:", "版　　次:", "版次:"}
    label_match = label + ":"
    i = 0
    start = None
    initial_tail: str | None = None
    while i < len(lines):
        if lines[i] == label_match:
            start = i + 1
            break
        if lines[i].startswith(label_match):
            initial_tail = lines[i][len(label_match):].strip() or None
            start = i + 1
            break
        i += 1
    if start is None:
        return None if initial_tail in (None, "") else initial_tail
    values: list[str] = []
    if initial_tail:
        values.append(initial_tail)
    j = start
    while j < len(lines):
        ln = lines[j]
        # Stop at the next known key
        if any(ln == k or ln.startswith(k) for k in stop_keys):
            break
        # Skip pure-noise lines: standalone digits, 条评论, rating numbers etc.
        if re.fullmatch(r"\d+", ln) or "条评论" in ln or ln in ("★", "☆") or re.fullmatch(r"[¥￥]?\s*\d+(\.\d+)?", ln):
            j += 1
            continue
        values.append(ln)
        j += 1
    joined = " ".join(v for v in values if v).strip()
    return joined or None


def _norm_noise(s: str) -> str:
    """Punctuation-agnostic form so '大卫·格雷恩' matches h1 variant '大卫格雷恩'."""
    return re.sub(
        r"[\s·.．,，、:：\-\[\]\(\)（）【】《》\"'“”‘’/\\]+",
        "",
        s or "",
    ).lower()


def _clean_h1_title(h1_text: str, author: str | None, publisher: str | None) -> tuple[str, str | None]:
    """Dangdang h1 usually mixes title, author, publisher, ads.

    Strategy: strip known author / publisher text and common noise tokens
    (both exact and punctuation-agnostic variants), then split on first "：".
    """
    raw = (h1_text or "").strip().rstrip(".。·")
    raw = re.sub(r"\s+", " ", raw)

    exact_tokens: list[str] = []
    for t in (author, publisher):
        if t:
            exact_tokens.append(t)
            exact_tokens.extend(x for x in re.split(r"\s+", t) if x)
    exact_tokens.extend([
        "全新正版", "正版", "当当自营", "自营", "可开发票", "现货", "包邮",
        "北京大学正版", "旗舰店", "专营店", "图书专营店",
        "全新", "正品", "书籍", "图书", "新华书店",
    ])
    fuzzy_tokens = [
        (t, fz)
        for t in exact_tokens
        if t
        # Skip single-chars (e.g. "美" from an author's country marker) so we
        # don't accidentally zap parts of real title words like "美国".
        for fz in [_norm_noise(t)]
        if len(fz) >= 2
    ]

    # --- Pass 1: exact-match removal ---
    changed = True
    cleaned = raw
    while changed:
        changed = False
        for t in sorted({x for x in exact_tokens if x}, key=len, reverse=True):
            idx = cleaned.find(t)
            if idx >= 0:
                cleaned = cleaned[:idx] + " " + cleaned[idx + len(t):]
                changed = True

    # --- Pass 2: punctuation-agnostic fuzzy removal ---
    changed = True
    while changed:
        changed = False
        n_cleaned = _norm_noise(cleaned)
        candidates = sorted(
            ((orig, fz) for orig, fz in fuzzy_tokens if fz and fz in n_cleaned),
            key=lambda p: len(p[1]), reverse=True,
        )
        for orig, fz in candidates:
            idx_fz = n_cleaned.find(fz)
            if idx_fz < 0:
                continue
            s = e = -1
            n_i = 0
            for c_i, ch in enumerate(cleaned):
                norm_ch = _norm_noise(ch)
                if not norm_ch:
                    continue
                if n_i == idx_fz:
                    s = c_i
                if s >= 0 and n_i >= idx_fz + len(fz) - 1:
                    e = c_i + 1
                    break
                n_i += 1
            if s >= 0 and e < 0:
                e = len(cleaned)
            if s >= 0:
                cleaned = cleaned[:s] + " " + cleaned[e:]
                changed = True
                break
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:·.。,，、|")

    # Split on first standalone "：" / ":"
    m = re.match(r"^(.+?)[：:]\s*(.+)$", cleaned)
    if m:
        main = m.group(1).strip()
        sub = m.group(2).strip()
        if main and sub:
            return main, sub
    return cleaned, None


def fetch_product(url: str) -> dict:
    page_url = normalize_dangdang_url(url)
    try:
        resp = fetch_with_retry(
            session,
            page_url,
            headers={"Referer": "https://search.dangdang.com/"},
        )
    except requests.RequestException as exc:
        raise ValueError(f"访问当当商品页失败：{exc}") from exc
    if resp is None:
        raise ValueError("无法访问当当商品页（网络超时或连接失败，已重试数次）")
    if resp.status_code != 200:
        raise ValueError(f"无法访问当当商品页（HTTP {resp.status_code}）")

    soup = BeautifulSoup(resp.text, "lxml")

    h1 = soup.select_one("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""

    # 1. Parse structured meta from `div.messbox_info` (most reliable block)
    messbox = soup.select_one("div.messbox_info") or soup.select_one("#product_info")
    mess_text = messbox.get_text("\n", strip=True) if messbox else ""

    author = _messbox_kv(mess_text, "作者")
    translator = _messbox_kv(mess_text, "译者")
    publisher = _messbox_kv(mess_text, "出版社")

    # 2. Clean the title using author/publisher as separators
    title, subtitle = _clean_h1_title(h1_text, author, publisher)
    if not title:
        # Last-resort: if h1 was all noise, try again without separator trimming
        title = (h1_text or "").strip()[:200]
    if not title:
        raise ValueError("未能解析书名")

    # 3. Cover → #largePic / #main-img-slider / div.pic img
    cover_url: str | None = None
    for sel in ("#largePic", "#main-img-slider img", "div.pic img", ".product_pic img"):
        el = soup.select_one(sel)
        if not el:
            continue
        src = el.get("src") or el.get("data-src") or el.get("data-original")
        if src:
            cover_url = src.strip()
            break
    if cover_url and cover_url.startswith("//"):
        cover_url = "https:" + cover_url

    # 4. ISBN — not always present in messbox_info, scan the whole page
    isbn: str | None = None
    if mess_text:
        m = re.search(r"ISBN[:：]?\s*([\dXx-]{10,17})", mess_text)
        if m:
            isbn = m.group(1).replace("-", "").strip()
    if not isbn:
        all_text = soup.get_text("\n", strip=True)
        m = re.search(r"ISBN[:：]?\s*([\dXx-]{10,17})", all_text)
        if m:
            isbn = m.group(1).replace("-", "").strip()

    pid = extract_product_id(page_url)
    return {
        "dangdang_id": pid,
        "dangdang_url": page_url,
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "translator": translator,
        "isbn": isbn,
        "publisher": publisher,
        "cover_url": cover_url,
    }
