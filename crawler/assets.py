# -*- coding: utf-8 -*-
"""
assets.py — Tải ảnh và tệp đính kèm (văn bản) của mỗi bản ghi về máy.

Dùng SimpleFetcher (requests) để tải nhị phân — nhanh và tôn trọng robots/rate
limit. Trả về danh sách mô tả tệp đã tải để ghi vào bản ghi JSON (đường dẫn nội
bộ + URL gốc), nhờ đó dữ liệu "kèm hình ảnh, không bỏ sót".
"""

from __future__ import annotations
import os

from .fetcher import SimpleFetcher
from .utils import ensure_dir, safe_filename, url_hash, get_logger

log = get_logger()


class AssetDownloader:
    def __init__(self, settings, storage):
        self.s = settings
        self.storage = storage
        # Luôn dùng SimpleFetcher cho tải tệp (kể cả khi crawl bằng browser).
        self._dl = SimpleFetcher(settings)

    def _download_list(self, urls, dest_dir, kind):
        results = []
        for u in urls:
            fname = safe_filename(u)
            if not fname or "." not in fname:
                fname = f"{kind}_{url_hash(u)}"
            path = os.path.join(dest_dir, fname)
            # tránh trùng tên
            if os.path.exists(path):
                path = os.path.join(dest_dir, f"{url_hash(u)}_{fname}")
            ok = self._dl.download(u, path)
            results.append({
                "source_url": u,
                "local_path": os.path.relpath(path, self.s.data_dir) if ok else None,
                "kind": kind,
                "downloaded": ok,
            })
            if ok:
                log.info("   ↓ %s: %s", kind, fname)
            else:
                log.warning("   ✗ Không tải được %s: %s", kind, u)
        return results

    def download_for_record(self, record: dict, category_key: str, rec_id: str) -> dict:
        """Tải toàn bộ ảnh + đính kèm của 1 bản ghi. Trả về dict tóm tắt."""
        if not self.s.download_assets:
            return {"images": [], "attachments": []}

        dest = self.storage.assets_dir(category_key, rec_id)
        img_dir = ensure_dir(os.path.join(dest, "images"))
        att_dir = ensure_dir(os.path.join(dest, "attachments"))

        images = self._download_list(record.get("images", []), img_dir, "image")
        attachments = self._download_list(record.get("attachments", []), att_dir,
                                            "attachment")
        return {"images": images, "attachments": attachments}
