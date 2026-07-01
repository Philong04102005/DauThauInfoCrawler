# -*- coding: utf-8 -*-
"""
main.py — Điểm chạy chính (CLI) cho crawler dauthau.asia.

Ví dụ dùng:
  python main.py                         # crawl mọi danh mục đang bật
  python main.py --category van_ban_dau_thau
  python main.py --max-pages 2 --max-items 10     # chạy thử nhanh
  python main.py --no-assets             # không tải ảnh/tệp
  python main.py --show-browser          # hiện trình duyệt (debug)
  python main.py --list                  # liệt kê các danh mục

Chi tiết cấu hình xem config.py và README.md.
"""

from __future__ import annotations
import argparse
import sys
import os

# đảm bảo import được config.py và package crawler khi chạy từ thư mục này
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as user_config
from crawler.config_bridge import load_settings
from crawler.utils import setup_logging
from crawler.storage import Storage
from crawler.engine import CrawlEngine
from crawler.fetcher import make_fetcher


def build_argparser():
    p = argparse.ArgumentParser(
        description="Crawler thu thập dữ liệu công khai từ dauthau.asia -> JSON + SQLite."
    )
    p.add_argument("--category", "-c", action="append",
                    help="Chỉ crawl danh mục theo key (có thể lặp lại). Mặc định: tất cả.")
    p.add_argument("--list", action="store_true", help="Liệt kê các danh mục rồi thoát.")
    p.add_argument("--max-pages", type=int, help="Số trang danh sách tối đa mỗi danh mục.")
    p.add_argument("--max-items", type=int, help="Số bản ghi tối đa mỗi danh mục.")
    p.add_argument("--delay", type=float, help="Giây nghỉ giữa các request.")
    p.add_argument("--data-dir", help="Thư mục lưu dữ liệu (ghi đè config).")
    p.add_argument("--no-assets", action="store_true", help="Không tải ảnh/tệp đính kèm.")
    p.add_argument("--no-browser", action="store_true",
                    help="Dùng requests thay vì trình duyệt (chỉ hợp trang tĩnh).")
    p.add_argument("--show-browser", action="store_true",
                    help="Hiện cửa sổ trình duyệt (headless=False) để debug.")
    p.add_argument("--log-level", default="INFO",
                    help="DEBUG | INFO | WARNING | ERROR.")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)

    if args.list:
        print("Các danh mục cấu hình trong config.py:\n")
        for c in user_config.CATEGORIES:
            flag = "✓" if c.get("enabled", True) else "·"
            print(f"  [{flag}] {c['key']:<22} {c['name']}")
            print(f"        {c['list_url']}")
        return 0

    settings = load_settings()
    settings.apply_overrides(
        max_pages_per_category=args.max_pages,
        max_items_per_category=args.max_items,
        request_delay=args.delay,
        data_dir=args.data_dir,
        download_assets=False if args.no_assets else None,
        use_browser=False if args.no_browser else None,
        headless=False if args.show_browser else None,
    )

    log = setup_logging(args.log_level,
                        log_file=os.path.join(settings.data_dir, "crawl.log"))
    log.info("Khởi động crawler dauthau.asia")
    log.info("Thư mục dữ liệu: %s", settings.data_dir)
    log.info("Chế độ trình duyệt: %s | Tải tệp: %s | Delay: %.1fs",
            settings.use_browser, settings.download_assets, settings.request_delay)

    # chọn danh mục
    if args.category:
        cats = [user_config.get_category(k) for k in args.category]
        cats = [c for c in cats if c]
        if not cats:
            log.error("Không tìm thấy danh mục nào khớp %s", args.category)
            return 1
    else:
        cats = user_config.enabled_categories()

    log.info("Sẽ crawl %d danh mục: %s", len(cats), ", ".join(c["key"] for c in cats))

    storage = Storage(settings)
    engine = CrawlEngine(settings, storage)

    fetcher = make_fetcher(settings)
    try:
        # BrowserFetcher cần start/close; SimpleFetcher thì không.
        if hasattr(fetcher, "start"):
            fetcher.start()
        engine.run(fetcher, cats)
    finally:
        if hasattr(fetcher, "close"):
            fetcher.close()
        storage.close()

    log.info("XONG. Dữ liệu nằm trong: %s", settings.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
