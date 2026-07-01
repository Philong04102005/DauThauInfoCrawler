# -*- coding: utf-8 -*-
"""utils.py — Tiện ích dùng chung: logging, URL, hashing, slug."""

from __future__ import annotations
import hashlib
import logging
import os
import re
import unicodedata
from urllib.parse import urljoin, urlparse, urldefrag

_LOG_CONFIGURED = False


def setup_logging(level: str = "INFO", log_file: str | None = None) -> logging.Logger:
    """Khởi tạo logger gốc, in ra console và (tuỳ chọn) file."""
    global _LOG_CONFIGURED
    logger = logging.getLogger("dauthau")
    if _LOG_CONFIGURED:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    _LOG_CONFIGURED = True
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("dauthau")


def normalize_url(base: str, href: str) -> str | None:
    """Chuẩn hoá URL tương đối -> tuyệt đối, bỏ fragment (#...)."""
    if not href:
        return None
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
        return None
    absolute = urljoin(base, href)
    absolute, _ = urldefrag(absolute)
    return absolute


def same_domain(url: str, base_url: str) -> bool:
    try:
        return urlparse(url).netloc == urlparse(base_url).netloc
    except Exception:
        return False


def url_hash(url: str) -> str:
    """Hash ngắn ổn định cho URL — dùng làm id/tên file."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def slugify(text: str, max_len: int = 80) -> str:
    """Biến chuỗi (kể cả tiếng Việt có dấu) thành slug an toàn cho tên file."""
    if not text:
        return "untitled"
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text[:max_len] or "untitled"


def safe_filename(name: str, max_len: int = 120) -> str:
    """Làm sạch tên file (giữ phần mở rộng)."""
    name = name.split("?")[0].split("#")[0]
    name = os.path.basename(name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    if len(name) > max_len:
        root, ext = os.path.splitext(name)
        name = root[: max_len - len(ext)] + ext
    return name or "file"


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path
