# -*- coding: utf-8 -*-
"""
parser.py — Trích xuất dữ liệu có cấu trúc từ HTML.

Chiến lược "generic + bền": vì trang có thể đổi giao diện và mỗi danh mục có
bố cục khác nhau, parser KHÔNG phụ thuộc vào tên class cố định. Thay vào đó nó
trích xuất (đã GIỚI HẠN vào vùng nội dung chính để loại menu/banner/footer):
  * title            : tiêu đề (h1 > title > og:title)
  * fields           : mọi cặp khoá–giá trị tìm được trong bảng 2 cột, bảng
                       3 cột dạng "nhãn : giá trị", <dl>, và các dòng
                       <strong>Nhãn:</strong> giá trị.
  * tables           : TOÀN BỘ bảng nhiều cột (header + rows) — nơi chứa dữ
                       liệu dạng danh sách (vd: kết quả lựa chọn nhà thầu).
  * text             : toàn văn nội dung chính (đã loại menu/script).
  * images           : ảnh trong nội dung (URL tuyệt đối, đã lọc icon/banner).
  * attachments      : link tới tệp .pdf/.doc/.xls/.zip... (văn bản đính kèm).
  * links            : mọi link nội bộ (để dò trang chi tiết / phân trang).
  * meta             : thẻ meta (description, keywords, og:*).
  * requires_login   : True nếu trang che nội dung yêu cầu đăng nhập/VIP.

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

# Selector vùng nội dung chính mặc định (có thể ghi đè qua config).
_DEFAULT_MAIN_SELECTORS = [
    "div.col-main-inner", "div.col-main", "#siteContent", "div.content",
]

# Dấu hiệu nội dung bị che, yêu cầu đăng nhập / nâng cấp gói.
_LOGIN_WALL_PATTERNS = [
    "đăng nhập để xem", "vui lòng đăng nhập", "cần đăng nhập",
    "nâng cấp gói", "dành cho thành viên", "đăng ký gói vip",
]


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def _main_content(soup: BeautifulSoup, settings=None) -> BeautifulSoup:
    """Trả về node NỘI DUNG CHÍNH (thử lần lượt selector); fallback = cả trang."""
    selectors = None
    if settings is not None:
        selectors = getattr(settings, "main_content_selectors", None)
    for sel in (selectors or _DEFAULT_MAIN_SELECTORS):
        try:
            node = soup.select_one(sel)
        except Exception:
            node = None
        if node and _clean_text(node.get_text())[:50]:
            return node
    return soup.body or soup


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


def extract_fields(root: BeautifulSoup) -> dict:
    """Lấy các cặp khoá–giá trị từ <table>, <dl> và dòng <strong>Nhãn:</strong>."""
    fields: dict[str, str] = {}

    def _add(k: str, v: str):
        k = _clean_text(k).rstrip(":").strip()
        v = _clean_text(v)
        if k and v and len(k) < 200:
            fields.setdefault(k, v)

    for table in root.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            # Bảng 2 cột: nhãn | giá trị
            if len(cells) == 2:
                _add(cells[0].get_text(), cells[1].get_text())
            # Bảng 3 cột dạng: nhãn | : | giá trị
            elif len(cells) == 3 and _clean_text(cells[1].get_text()) in (":", "", "-"):
                _add(cells[0].get_text(), cells[2].get_text())

    # Danh sách định nghĩa <dl><dt>..<dd>..
    for dl in root.find_all("dl"):
        dts = dl.find_all("dt")
        dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            _add(dt.get_text(), dd.get_text())

    # Dòng kiểu <li>/<p>/<div> chứa <strong>Nhãn:</strong> giá trị
    for el in root.find_all(["li", "p", "div"]):
        b = el.find(["strong", "b"], recursive=False)
        if not b:
            continue
        label = _clean_text(b.get_text())
        if not label or ":" not in label + ":" or len(label) > 120:
            continue
        full = _clean_text(el.get_text())
        if full.startswith(label):
            value = full[len(label):].lstrip(":").strip()
            if value and label.rstrip(":"):
                _add(label, value)

    return fields


def extract_tables(root: BeautifulSoup) -> list[dict]:
    """Trích TOÀN BỘ bảng nhiều cột (>=3) thành {headers, rows} để không sót
    dữ liệu dạng danh sách (vd: danh sách nhà thầu trúng, giá gói thầu...)."""
    tables = []
    for table in root.find_all("table"):
        rows_el = table.find_all("tr")
        if not rows_el:
            continue
        n_cols = max(len(r.find_all(["th", "td"])) for r in rows_el)
        if n_cols < 3:
            continue  # bảng 2 cột đã vào 'fields'
        headers: list[str] = []
        rows: list[list[str]] = []
        for i, r in enumerate(rows_el):
            cells = [_clean_text(c.get_text()) for c in r.find_all(["th", "td"])]
            if i == 0 and r.find("th"):
                headers = cells
            else:
                if any(cells):
                    rows.append(cells)
        if rows or headers:
            tables.append({"headers": headers, "rows": rows})
    return tables


def extract_main_text(root: BeautifulSoup) -> str:
    clone = _soup(str(root))
    for tag in clone.find_all(_NOISE_TAGS):
        tag.decompose()
    return _clean_text(clone.get_text(separator="\n"))


def _image_blacklisted(url: str, settings=None) -> bool:
    bl = getattr(settings, "image_url_blacklist", None) or []
    low = url.lower()
    return any(pat.lower() in low for pat in bl)


def extract_images(root: BeautifulSoup, base_url: str, settings=None) -> list[str]:
    urls = set()
    for img in root.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        u = normalize_url(base_url, src)
        if u and not u.startswith("data:") and not _image_blacklisted(u, settings):
            urls.add(u)
    return sorted(urls)


def extract_attachments(root: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in root.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u and u.lower().split("?")[0].endswith(ATTACHMENT_EXT):
            urls.add(u)
        # Link tải file qua handler (vd /download/, ?download=) cũng là đính kèm.
        elif u and re.search(r"(/download/|[?&](download|file)=)", u, re.I):
            urls.add(u)
    return sorted(urls)


def extract_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    urls = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u:
            urls.add(u)
    return sorted(urls)


def detect_login_wall(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in _LOGIN_WALL_PATTERNS)


def parse_detail(html: str, url: str, base_url: str, settings=None) -> dict:
    """Phân tích một trang CHI TIẾT thành 1 bản ghi có cấu trúc."""
    soup = _soup(html)
    meta = extract_meta(soup)
    main = _main_content(soup, settings)
    text = extract_main_text(main)
    record = {
        "url": url,
        "title": extract_title(soup, meta),
        "fields": extract_fields(main),
        "tables": extract_tables(main),
        "text": text,
        "images": extract_images(main, base_url, settings),
        "attachments": extract_attachments(main, base_url),
        "meta": meta,
        "requires_login": detect_login_wall(text),
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
        if re.search(r"/page-\d+", path) or re.search(r"[?&]page=\d+", u):
            continue  # link phân trang, không phải chi tiết
        if contains and contains in u and path != list_url and len(path) > len(list_url):
            detail_links.add(u)

    # Link phân trang: dạng ?page=N hoặc /page-N
    page_links = set()
    for a in soup.find_all("a", href=True):
        u = normalize_url(base_url, a["href"])
        if u and (re.search(r"[?&]page=\d+", u) or re.search(r"/page-\d+", u)):
            page_links.add(u)

    return {
        "detail_links": sorted(detail_links),
        "page_links": sorted(page_links),
    }
