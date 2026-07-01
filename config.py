# -*- coding: utf-8 -*-
"""
config.py — Cấu hình trung tâm cho crawler dauthau.asia

Toàn bộ hành vi của crawler được điều khiển từ đây. Bạn KHÔNG cần sửa code lõi;
chỉ cần chỉnh các giá trị dưới đây (danh mục, selector, tốc độ...).

Trang dauthau.asia render nội dung bằng JavaScript, nên mặc định crawler dùng
trình duyệt headless (Playwright). Xem README.md để biết cách cài đặt.
"""

from __future__ import annotations
import os

# ---------------------------------------------------------------------------
# 1. CẤU HÌNH CHUNG
# ---------------------------------------------------------------------------

BASE_URL = "https://dauthau.asia"

# Thư mục lưu dữ liệu. Mặc định: ./data cạnh file này.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# User-Agent khai báo trung thực + link liên hệ (nên đặt email của bạn).
USER_AGENT = (
    "DauThauResearchBot/1.0 (+lien-he: philong04102005@gmail.com) "
    "Python-Playwright"
)

# Ngôn ngữ giao diện muốn crawl: "vi" hoặc "en"
LANGUAGE = "vi"

# --- Lịch sự & an toàn ------------------------------------------------------
RESPECT_ROBOTS_TXT = True     # Tôn trọng robots.txt (nên để True)
REQUEST_DELAY = 2.0           # Giây nghỉ tối thiểu giữa 2 request (điều tiết tải)
RANDOM_JITTER = 1.0           # Cộng thêm ngẫu nhiên 0..JITTER giây để tự nhiên hơn
MAX_RETRIES = 3               # Số lần thử lại khi lỗi mạng
RETRY_BACKOFF = 5.0           # Giây, nhân theo cấp số cho mỗi lần retry
PAGE_TIMEOUT = 45000          # Timeout tải trang (ms) cho Playwright
NAV_WAIT_UNTIL = "networkidle"  # "load" | "domcontentloaded" | "networkidle"

# --- Trình duyệt ------------------------------------------------------------
USE_BROWSER = True            # True: dùng Playwright (bắt buộc cho trang JS)
HEADLESS = True              # False để xem trình duyệt chạy (debug)
BLOCK_RESOURCES = ["font", "media"]  # Chặn tải để nhanh hơn. Đừng chặn "image"
                                     # nếu bạn muốn tải ảnh trong nội dung.

# --- Giới hạn (đặt None để không giới hạn) ----------------------------------
MAX_PAGES_PER_CATEGORY = 5    # Số trang danh sách tối đa mỗi danh mục (an toàn khi test)
MAX_ITEMS_PER_CATEGORY = None # Số bản ghi tối đa mỗi danh mục
DOWNLOAD_ASSETS = True        # Tải ảnh + tệp đính kèm về máy
CAPTURE_XHR_JSON = True       # Lưu lại mọi phản hồi JSON/XHR (API ẩn) khi render

# --- Lưu trữ ----------------------------------------------------------------
SAVE_JSON = True              # Lưu mỗi bản ghi thành 1 file .json
SAVE_SQLITE = True            # Đồng thời ghi vào SQLite để tra cứu/lọc nhanh
SQLITE_FILE = os.path.join(DATA_DIR, "dauthau.sqlite")
SAVE_RAW_HTML = True          # Lưu HTML gốc của trang chi tiết (để parse lại sau)

# ---------------------------------------------------------------------------
# 2. DANH MỤC CẦN CRAWL
# ---------------------------------------------------------------------------
# Mỗi danh mục là một "nguồn" list -> detail.
#   key              : định danh nội bộ (dùng làm tên thư mục + bảng)
#   name             : tên hiển thị
#   list_url         : URL trang danh sách (bắt đầu crawl từ đây)
#   page_param       : tham số phân trang trên URL (vd '?page=' -> ?page=2).
#                      Nếu None, engine sẽ thử tìm nút "Trang sau".
#   detail_link_sel  : CSS selector tới các link chi tiết trong trang danh sách.
#                      Để None => engine tự động lấy mọi <a> trỏ vào detail_url_contains.
#   detail_url_contains: chuỗi phải có trong URL để coi là link chi tiết hợp lệ.
#   enabled          : bật/tắt danh mục này.
#
# LƯU Ý: các selector dưới đây là điểm khởi đầu hợp lý. Vì trang render JS và
# có thể đổi giao diện, hãy chạy thử 1 danh mục với HEADLESS=False rồi tinh
# chỉnh 'detail_link_sel' cho khớp. Engine có cơ chế tự-dò link nên vẫn chạy
# được ngay cả khi selector chưa chuẩn.

CATEGORIES = [
    {
        "key": "van_ban_dau_thau",
        "name": "Văn bản đấu thầu (pháp luật)",
        "list_url": f"{BASE_URL}/van-ban-dau-thau/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/van-ban-dau-thau/",
        "enabled": True,
    },
    {
        "key": "thongbao_moithau",
        "name": "Thông báo mời thầu (TBMT)",
        "list_url": f"{BASE_URL}/thongbao/moithau/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/thongbao/moithau/",
        "enabled": True,
    },
    {
        "key": "thongbao_moidautu",
        "name": "Thông báo mời đầu tư",
        "list_url": f"{BASE_URL}/thongbao/moidautu/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/thongbao/moidautu/",
        "enabled": True,
    },
    {
        "key": "kehoach_nhathau",
        "name": "Kế hoạch lựa chọn nhà thầu",
        "list_url": f"{BASE_URL}/kehoach/luachon-nhathau/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/kehoach/",
        "enabled": True,
    },
    {
        "key": "kehoach_nhadautu",
        "name": "Kế hoạch lựa chọn nhà đầu tư",
        "list_url": f"{BASE_URL}/kehoach/luachon-nhadautu/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/kehoach/",
        "enabled": True,
    },
    {
        "key": "ketqua_nhathau",
        "name": "Kết quả lựa chọn nhà thầu",
        "list_url": f"{BASE_URL}/ketqua/luachon-nhathau/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/ketqua/",
        "enabled": True,
    },
    {
        "key": "ketqua_nhadautu",
        "name": "Kết quả lựa chọn nhà đầu tư",
        "list_url": f"{BASE_URL}/ketqua/luachon-nhadautu/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/ketqua/",
        "enabled": True,
    },
    {
        "key": "nha_thau",
        "name": "Danh bạ nhà thầu / doanh nghiệp",
        "list_url": f"{BASE_URL}/businesslistings/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/businesslistings/",
        "enabled": True,
    },
    {
        "key": "to_chuc",
        "name": "Tổ chức / Chủ đầu tư / Bên mời thầu",
        "list_url": f"{BASE_URL}/to-chuc/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/to-chuc/",
        "enabled": True,
    },
    {
        "key": "hang_hoa",
        "name": "Hàng hóa",
        "list_url": f"{BASE_URL}/hanghoa/",
        "page_param": "?page=",
        "detail_link_sel": None,
        "detail_url_contains": "/hanghoa/",
        "enabled": True,
    },
]


def enabled_categories():
    """Trả về danh sách danh mục đang bật."""
    return [c for c in CATEGORIES if c.get("enabled", True)]


def get_category(key: str):
    for c in CATEGORIES:
        if c["key"] == key:
            return c
    return None
