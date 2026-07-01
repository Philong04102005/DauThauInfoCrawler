# -*- coding: utf-8 -*-
"""
storage.py — Lưu trữ dữ liệu: JSON (mỗi bản ghi 1 file) + SQLite (index tra cứu).

Bố cục thư mục data/:
  data/
  ├── dauthau.sqlite                 # CSDL tra cứu nhanh (mọi bản ghi)
  ├── <category>/
  │   ├── json/<id>.json             # bản ghi có cấu trúc
  │   ├── html/<id>.html             # HTML gốc (nếu SAVE_RAW_HTML)
  │   └── assets/<id>/...            # ảnh + tệp đính kèm của bản ghi
  └── _state.json                    # tiến độ để resume

Bảng SQLite 'records' lưu các trường chính + cột 'fields_json'/'raw_json' để
tra cứu toàn bộ. Có bảng FTS (full-text) để tìm theo từ khoá tiếng Việt.
"""

from __future__ import annotations
import json
import os
import sqlite3
import time
from typing import Any

from .utils import ensure_dir, get_logger

log = get_logger()


class Storage:
    def __init__(self, settings):
        self.s = settings
        ensure_dir(settings.data_dir)
        self.db = None
        if settings.save_sqlite:
            self._init_db()

    # -- SQLite -------------------------------------------------------------
    def _init_db(self):
        self.db = sqlite3.connect(self.s.sqlite_file)
        self.db.execute("PRAGMA journal_mode=WAL;")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id           TEXT PRIMARY KEY,
                category     TEXT,
                url          TEXT UNIQUE,
                title        TEXT,
                text         TEXT,
                fields_json  TEXT,
                images_json  TEXT,
                attachments_json TEXT,
                meta_json    TEXT,
                crawled_at   TEXT
            );
            """
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_cat ON records(category);")
        # Bảng full-text search (nếu SQLite hỗ trợ FTS5).
        try:
            self.db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS records_fts "
                "USING fts5(id, title, text, content='');"
            )
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False
            log.warning("SQLite không có FTS5 — bỏ qua full-text index.")
        self.db.commit()

    def upsert(self, record: dict, category_key: str, rec_id: str):
        if not self.db:
            return
        self.db.execute(
            """
            INSERT INTO records
              (id, category, url, title, text, fields_json, images_json,
               attachments_json, meta_json, crawled_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              title=excluded.title, text=excluded.text,
              fields_json=excluded.fields_json, images_json=excluded.images_json,
              attachments_json=excluded.attachments_json,
              meta_json=excluded.meta_json, crawled_at=excluded.crawled_at
            """,
            (
                rec_id, category_key, record.get("url"), record.get("title"),
                record.get("text", "")[:500000],
                json.dumps(record.get("fields", {}), ensure_ascii=False),
                json.dumps(record.get("images", []), ensure_ascii=False),
                json.dumps(record.get("attachments", []), ensure_ascii=False),
                json.dumps(record.get("meta", {}), ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        if getattr(self, "_fts", False):
            self.db.execute("DELETE FROM records_fts WHERE id=?", (rec_id,))
            self.db.execute(
                "INSERT INTO records_fts (id, title, text) VALUES (?,?,?)",
                (rec_id, record.get("title", ""), record.get("text", "")),
            )
        self.db.commit()

    def url_exists(self, url: str) -> bool:
        if not self.db:
            return False
        cur = self.db.execute("SELECT 1 FROM records WHERE url=? LIMIT 1", (url,))
        return cur.fetchone() is not None

    # -- JSON / file --------------------------------------------------------
    def category_dir(self, category_key: str) -> str:
        return ensure_dir(os.path.join(self.s.data_dir, category_key))

    def save_json(self, record: dict, category_key: str, rec_id: str) -> str:
        d = ensure_dir(os.path.join(self.category_dir(category_key), "json"))
        path = os.path.join(d, f"{rec_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return path

    def save_html(self, html: str, category_key: str, rec_id: str) -> str:
        d = ensure_dir(os.path.join(self.category_dir(category_key), "html"))
        path = os.path.join(d, f"{rec_id}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path

    def assets_dir(self, category_key: str, rec_id: str) -> str:
        return ensure_dir(os.path.join(self.category_dir(category_key),
                                        "assets", rec_id))

    def save_xhr(self, payloads: list, category_key: str, rec_id: str):
        if not payloads:
            return
        d = ensure_dir(os.path.join(self.category_dir(category_key), "xhr"))
        with open(os.path.join(d, f"{rec_id}.json"), "w", encoding="utf-8") as f:
            json.dump(payloads, f, ensure_ascii=False, indent=2)

    # -- state (resume) -----------------------------------------------------
    def _state_path(self) -> str:
        return os.path.join(self.s.data_dir, "_state.json")

    def load_state(self) -> dict:
        try:
            with open(self._state_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"done_urls": [], "categories": {}}

    def save_state(self, state: dict):
        with open(self._state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def close(self):
        if self.db:
            self.db.close()

    # -- xuất gộp -----------------------------------------------------------
    def export_category_ndjson(self, category_key: str) -> str | None:
        """Gộp toàn bộ JSON của 1 danh mục thành 1 file .ndjson (mỗi dòng 1 bản ghi)."""
        jdir = os.path.join(self.category_dir(category_key), "json")
        if not os.path.isdir(jdir):
            return None
        out = os.path.join(self.category_dir(category_key), f"{category_key}_all.ndjson")
        with open(out, "w", encoding="utf-8") as fo:
            for name in sorted(os.listdir(jdir)):
                if name.endswith(".json"):
                    with open(os.path.join(jdir, name), encoding="utf-8") as fi:
                        fo.write(fi.read().replace("\n", " ").strip() + "\n")
        return out
