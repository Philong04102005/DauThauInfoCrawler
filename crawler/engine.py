# -*- coding: utf-8 -*-
"""
engine.py — Điều phối toàn bộ quá trình crawl.

Luồng cho mỗi danh mục:
  1. Duyệt các trang DANH SÁCH (phân trang qua ?page=N) tới giới hạn cấu hình.
  2. Gom mọi link CHI TIẾT (kèm cơ chế tự-dò trong parser).
  3. Với mỗi link chi tiết: render -> parse -> tải ảnh/đính kèm -> lưu JSON+SQLite.
  4. Ghi tiến độ vào _state.json để có thể RESUME khi chạy lại (bỏ qua URL đã xong).

An toàn: tôn trọng robots.txt, rate limit, retry (đã cài trong fetcher).
"""

from __future__ import annotations
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from . import parser as P
from .assets import AssetDownloader
from .utils import get_logger, url_hash

log = get_logger()


def _with_page(url: str, page: int) -> str:
    """Trả về URL với tham số page=<page>."""
    parts = urlparse(url)
    q = parse_qs(parts.query)
    q["page"] = [str(page)]
    new_q = urlencode({k: v[0] for k, v in q.items()})
    return urlunparse(parts._replace(query=new_q))


class CrawlEngine:
    def __init__(self, settings, storage):
        self.s = settings
        self.storage = storage
        self.assets = AssetDownloader(settings, storage)
        self.state = storage.load_state()
        self.done = set(self.state.get("done_urls", []))

    # -----------------------------------------------------------------
    def crawl_category(self, fetcher, category: dict):
        key = category["key"]
        name = category["name"]
        log.info("=" * 70)
        log.info("DANH MỤC: %s  (%s)", name, key)
        log.info("=" * 70)

        detail_urls: list[str] = []
        seen_detail: set[str] = set()

        max_pages = self.s.max_pages_per_category
        page = 1
        while True:
            if max_pages is not None and page > max_pages:
                break
            list_url = category["list_url"] if page == 1 else _with_page(
                category["list_url"], page)
            log.info("[list] Trang %d: %s", page, list_url)
            res = fetcher.get(list_url)
            if not res.ok:
                log.warning("Không tải được trang danh sách (%s). Dừng phân trang.",
                            res.error)
                break

            parsed = P.parse_list(res.html, res.final_url, self.s.base_url, category)
            new_links = [u for u in parsed["detail_links"] if u not in seen_detail]
            for u in new_links:
                seen_detail.add(u)
                detail_urls.append(u)
            log.info("  -> tìm thấy %d link chi tiết mới (tổng %d).",
                    len(new_links), len(detail_urls))

            # Điều kiện dừng phân trang: không có link mới => hết trang.
            if not new_links and page > 1:
                log.info("  Không còn link mới -> kết thúc phân trang.")
                break
            page += 1

        # --- crawl từng trang chi tiết ---
        max_items = self.s.max_items_per_category
        count = 0
        for url in detail_urls:
            if max_items is not None and count >= max_items:
                break
            if url in self.done or self.storage.url_exists(url):
                log.info("[skip] Đã có: %s", url)
                continue
            self._crawl_detail(fetcher, url, category)
            count += 1

        # xuất gộp ndjson cho danh mục
        out = self.storage.export_category_ndjson(key)
        if out:
            log.info("Đã xuất gộp: %s", out)
        log.info("HOÀN TẤT danh mục '%s': %d bản ghi mới.", name, count)

    # -----------------------------------------------------------------
    def _crawl_detail(self, fetcher, url: str, category: dict):
        key = category["key"]
        rec_id = url_hash(url)
        log.info("[detail] %s", url)
        res = fetcher.get(url)
        if not res.ok:
            log.warning("  Bỏ qua (lỗi %s).", res.error)
            return

        record = P.parse_detail(res.html, res.final_url, self.s.base_url)
        record["id"] = rec_id
        record["category"] = key
        record["category_name"] = category["name"]

        # Tải ảnh + đính kèm.
        asset_info = self.assets.download_for_record(record, key, rec_id)
        record["downloaded_assets"] = asset_info

        # Lưu.
        if self.s.save_raw_html:
            self.storage.save_html(res.html, key, rec_id)
        if getattr(res, "xhr_json", None):
            self.storage.save_xhr(res.xhr_json, key, rec_id)
        if self.s.save_json:
            self.storage.save_json(record, key, rec_id)
        if self.s.save_sqlite:
            self.storage.upsert(record, key, rec_id)

        # cập nhật state
        self.done.add(url)
        self.state["done_urls"] = sorted(self.done)
        self.storage.save_state(self.state)
        log.info("  ✔ Lưu xong (%d field, %d ảnh, %d đính kèm).",
                len(record.get("fields", {})),
                len(record.get("images", [])),
                len(record.get("attachments", [])))

    # -----------------------------------------------------------------
    def run(self, fetcher, categories: list[dict]):
        start = time.time()
        for cat in categories:
            try:
                self.crawl_category(fetcher, cat)
            except KeyboardInterrupt:
                log.warning("Bị ngắt bởi người dùng — tiến độ đã được lưu, có thể chạy lại để tiếp tục.")
                raise
            except Exception as e:  # noqa
                log.exception("Lỗi ở danh mục %s: %s", cat.get("key"), e)
        log.info("TỔNG THỜI GIAN: %.1f phút", (time.time() - start) / 60)
