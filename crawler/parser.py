# -*- coding: utf-8 -*-
"""
parser.py — Trích xuất dữ liệu có cấu trúc từ HTML.

Chiến lược "generic + bền": vì trang có thể đổi giao diện và mỗi danh mục có
bố cục khác nhau, parser KHÔNG phụ thuộc vào tên class cố định. Thay vào đó nó
trích xuất:
  * title            : tiêu đề (h1 > title > og:title)
  * fields           : mọi cặp khoá–giá trị tìm được trong các bảng và danh sách
                       định nghĩa (<table>, <dl>) — đây là nơi chứa hầu hết dữ
                       liệu chi tiết gói thầu/văn bản.
  * text             : toàn văn nội dung chính (đã loại menu/script).
  * images           : mọi ảnh trong nội dung (URL tuyệt đối).
  * attachments      : link tới tệp .pdf/.doc/.xls/.zip... (văn bản đính kèm).
  * links            : mọi link nội bộ (để dò trang chi tiết / phân trang).
  * meta             : thẻ meta (description, keywords, og:*).

Nhờ vậy dữ liệu thu được đầy đủ dù selector riêng chưa được tinh chỉnh.
"""

from __future__ import annotations
import re
from bs4 import BeautifulSoup

from .utils import normalize_url

# Đuôi tệp coi là "văn bản/tài liệu đính kèm" cần tải về.
ATTACHMENT_EXT = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".csv", ".txt", ".xml", ".rtf",
)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")

# Các phần tử không phải nội dung -> loại bỏ trước khi lấy text.
_NOISE_TAGS = ["script", "style", "nav", "header", "footer", "noscript",
                "form", "iframe", "svg"]


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def extract_meta(soup: BeautifulSoup) -> dict:
    meta = {}
    for m in soup.find_all("meta"):
        key = m.get("name") or m.get("property")
        val = m.get("content")
        if key and val:
            meta[key.strip()] = val.strip()
    return meta


def extract_title(soup: BeautifulSoup, meta: dict) -> str:
    if soup.h1 and _clean_text(soup.h1.get_text()):
        return _clean_text(soup.h1.get_text())
    if meta.get("og:title"):
        return meta["og:title"]
    if soup.title and _clean_text(soup.title.get_text()):
        return _clean_text(soup.title.get_text())
    return ""


def extract_fields(soup: BeautifulSoup) -> dict:
    """Lấy các cặp khoá–giá trị từ <table> và <dl>."""
    fields: dict[str, str] = {}

    # Bảng 2 cột: cột trái = nhãn, cột phải = giá trị.
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) == 2:
                k = _clean_text(cells[0].get_text())
                v = _clean_text(cells[1].get_text())
                if k and v and len(k) < 200:
                    fields.setdefault(k.rstrip(":"), v)

    # Danh sách định nghĩa <dl><dt>..<dd>..
    for dl in soup.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            k = _clean_text(dt.get_text())
            v = _clean_text(dd.get_text())
            if k and v:
                fields.setdefault(k.rstrip(":"), v)

    return fields


def extract_main_text(soup: BeautifulSoup) -> str:
    clone = _soup(str(soup))
    for tag in clone.find_all(_NOISE_TAGS):
        tag.decompose()
    return _clean_text(clone.get_text(separator="\n"))


def extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        u = normalize_url(base_url, src)
        if u and not u.startswith("data:"):
            urls.add(u)
    # ảnh khai báo trong og:image
    for m in soup.find_all("meta", property="og:image"):
        u = normalize_url(base_url, m.get("content"))
        if u:
            urls.add(u)
    return sorted(urls)


def extract_attachments(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u and u.lower().split("?")[0].endswith(ATTACHMENT_EXT):
            urls.add(u)
    return sorted(urls)


def extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u:
            urls.add(u)
    return sorted(urls)


def parse_detail(html: str, url: str, base_url: str) -> dict:
    """Phân tích một trang CHI TIẾT thành 1 bản ghi có cấu trúc."""
    soup = _soup(html)
    meta = extract_meta(soup)
    record = {
        "url": url,
        "title": extract_title(soup, meta),
        "fields": extract_fields(soup),
        "text": extract_main_text(soup),
        "images": extract_images(soup, base_url),
        "attachments": extract_attachments(soup, base_url),
        "meta": meta,
    }
    return record


def parse_list(html: str, url: str, base_url: str, category: dict) -> dict:
    """
    Phân tích một trang DANH SÁCH: trả về link chi tiết + link phân trang.
    """
    soup = _soup(html)
    detail_links: set[str] = set()

    sel = category.get("detail_link_sel")
    contains = category.get("detail_url_contains") or ""
    list_url = category["list_url"].rstrip("/")

    if sel:
        # Ưu tiên selector do người dùng cấu hình.
        for a in soup.select(sel):
            u = normalize_url(base_url, a.get("href"))
            if u:
                detail_links.add(u)

    # Luôn kèm cơ chế tự-dò: mọi <a> trỏ vào detail_url_contains, sâu hơn
    # chính URL danh sách (loại trừ chính trang list và trang phân trang).
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if not u:
            continue
        path = u.split("?")[0].rstrip("/")
        if contains and contains in u and path != list_url and len(path) > len(list_url):
            detail_links.add(u)

    # Link phân trang (chứa page=)
    page_links = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u and re.search(r"[?&]page=\d+", u):
            page_links.add(u)

    return {
        "detail_links": sorted(detail_links),
        "page_links": sorted(page_links),
    }
