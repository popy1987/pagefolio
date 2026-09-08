"""Douban book subject page parser."""

from __future__ import annotations

import re
import time

import requests
from requests.exceptions import ChunkedEncodingError as _ChunkedEncodingError
from bs4 import BeautifulSoup

from pagefolio.config import (
    DOUBAN_COOKIE,
    REQUEST_MAX_RETRIES,
    REQUEST_RETRY_BASE_DELAY,
    REQUEST_TIMEOUT,
    USER_AGENT,
)


def _inject_douban_cookies(session: requests.Session) -> None:
    """Apply logged-in Douban cookies (if configured) to bypass HTTP 403.

    The raw cookie string looks like:
        bid=xxxxx; __yadk_uid=xxxxx; _pk_id.100001.3ac3=xxxxx; ...
    """
    if not DOUBAN_COOKIE:
        return
    for chunk in DOUBAN_COOKIE.split(";"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k = k.strip()
        v = v.strip()
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
    """与 covers.fetch_with_retry 语义一致的封装：二元 timeout + 指数退避。

    - 只对 Timeout / ConnectionError / ChunkedEncodingError / 5xx 重试
    - 4xx 立即原样返回（403 表示 cookies 失效，404 表示链接错误，重试无意义）
    - 所有重试耗尽后返回 None 或最后一次 5xx 响应，不把网络异常向上抛
    """
    last_resp: requests.Response | None = None
    for attempt in range(max_retries):
        try:
            resp = sess.request(method, url, timeout=timeout, headers=headers, **kwargs)
            if resp.status_code in accept_status:
                return resp
            if 500 <= resp.status_code < 600:
                last_resp = resp
            else:
                return resp  # 4xx 直接给上层看 status_code
        except (requests.Timeout, requests.ConnectionError, _ChunkedEncodingError):
            # 瞬时网络异常：等下一循环重试
            pass
        except requests.RequestException:
            # TooManyRedirects 等确定性异常：立即放弃
            return None
        if attempt < max_retries - 1:
            time.sleep(base_delay * (2 ** attempt))
    return last_resp


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


def _norm_person_name(s: str) -> str:
    """人名规范化：去掉国别标记后的空格，如 '[美] 沃尔夫' → '[美]沃尔夫'。"""
    return re.sub(r"(\[[^\]]+\])\s+", r"\1", s or "").strip()


def _info_fields(info) -> dict[str, str]:
    """按 <span class='pl'>标签</span> 结构化提取豆瓣 #info 字段。

    豆瓣页面每行形如：
        <span class="pl">作者</span>: <a>甲</a> / <a>乙</a><br>
        <span class="pl">出版社:</span> 商务印书馆<br>
    「作者/译者」的冒号在 span 外侧，get_text 后标签与冒号间夹换行，
    "译者:" 类正则会失效；这里改为定位 span.pl 后顺序收集到 <br> 前的
    文本/链接节点，作者行与译者行天然分开，不会再把译者混进作者。
    """
    fields: dict[str, str] = {}
    if info is None:
        return fields
    for pl in info.select("span.pl"):
        label = pl.get_text(strip=True).rstrip(":：").strip()
        if not label or label in fields:
            continue
        # 先收集 <br> 前的纯文本节点与链接节点
        text_parts: list[str] = []
        anchors = []
        node = pl.next_sibling
        while node is not None and getattr(node, "name", None) != "br":
            if isinstance(node, str):
                text = str(node).strip(" /:\n\t\r")
                if text:
                    text_parts.append(_norm_person_name(text))
            elif getattr(node, "name", None) == "a":
                anchors.append(node)
            node = node.next_sibling
        # 同一作者在豆瓣上常有 /author/ 正式链接 + /search 备用链接两个入口，
        # 优先只取 /author/ 链接，避免同一人出现两次；没有时才退回全部链接
        if anchors:
            official = [a for a in anchors if "/author/" in (a.get("href") or "")]
            chosen = official or anchors
            parts = [_norm_person_name(a.get_text(strip=True)) for a in chosen if a.get_text(strip=True)]
        else:
            parts = text_parts
        if parts:
            fields[label] = "、".join(dict.fromkeys(parts))
    return fields


def fetch_subject(url: str) -> dict:
    page_url = normalize_douban_url(url)
    try:
        resp = fetch_with_retry(
            session,
            page_url,
            headers={"Referer": page_url},
        )
    except requests.RequestException as exc:
        raise ValueError(f"访问豆瓣页面失败：{exc}") from exc
    if resp is None:
        raise ValueError("无法访问豆瓣页面（网络超时或连接失败，已重试数次）")
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

    # #info 结构化字段：作者行/译者行分开提取，避免译者混入作者
    info = soup.select_one("#info")
    info_text = info.get_text("\n", strip=True) if info else ""
    fields = _info_fields(info)

    author = fields.get("作者")
    if not author:
        # 旧页面变体兜底：作者链接选择器（此时无法区分著/译，仅作 fallback）
        author_els = soup.select("#info a[href*='/author/'], #info a[href*='/search/'][href*='author']")
        author = "、".join(
            dict.fromkeys(_norm_person_name(el.get_text(strip=True)) for el in author_els)
        ) or None
    translator = fields.get("译者")
    if subtitle is None:
        subtitle = fields.get("副标题")

    return {
        "douban_id": extract_subject_id(page_url),
        "douban_url": page_url,
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "translator": translator,
        "isbn": fields.get("ISBN") or _info_value(info_text, "ISBN"),
        "publisher": fields.get("出版社") or _info_value(info_text, "出版社"),
        "cover_url": cover_url,
    }
