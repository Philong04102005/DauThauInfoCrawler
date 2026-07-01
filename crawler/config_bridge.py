# -*- coding: utf-8 -*-
"""
config_bridge.py — Gom các hằng số trong config.py thành một đối tượng Settings
có thể ghi đè bằng tham số dòng lệnh (CLI). Giúp code lõi không phụ thuộc trực
tiếp vào biến toàn cục.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import config as user_config


@dataclass
class Settings:
    base_url: str = user_config.BASE_URL
    data_dir: str = user_config.DATA_DIR
    user_agent: str = user_config.USER_AGENT
    language: str = user_config.LANGUAGE

    respect_robots: bool = user_config.RESPECT_ROBOTS_TXT
    request_delay: float = user_config.REQUEST_DELAY
    random_jitter: float = user_config.RANDOM_JITTER
    max_retries: int = user_config.MAX_RETRIES
    retry_backoff: float = user_config.RETRY_BACKOFF
    page_timeout: int = user_config.PAGE_TIMEOUT
    nav_wait_until: str = user_config.NAV_WAIT_UNTIL

    use_browser: bool = user_config.USE_BROWSER
    headless: bool = user_config.HEADLESS
    block_resources: list = field(default_factory=lambda: list(user_config.BLOCK_RESOURCES))

    max_pages_per_category: Any = user_config.MAX_PAGES_PER_CATEGORY
    max_items_per_category: Any = user_config.MAX_ITEMS_PER_CATEGORY
    download_assets: bool = user_config.DOWNLOAD_ASSETS
    capture_xhr_json: bool = user_config.CAPTURE_XHR_JSON

    save_json: bool = user_config.SAVE_JSON
    save_sqlite: bool = user_config.SAVE_SQLITE
    sqlite_file: str = user_config.SQLITE_FILE
    save_raw_html: bool = user_config.SAVE_RAW_HTML

    def apply_overrides(self, **kw):
        """Ghi đè các trường không phải None từ CLI."""
        for k, v in kw.items():
            if v is not None and hasattr(self, k):
                setattr(self, k, v)
        # Cập nhật đường dẫn phụ thuộc data_dir
        import os
        self.sqlite_file = os.path.join(self.data_dir, "dauthau.sqlite")
        return self


def load_settings() -> Settings:
    return Settings()
