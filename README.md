# Crawler dữ liệu đấu thầu — dauthau.asia

Bộ mã nguồn thu thập **dữ liệu công khai** từ [dauthau.asia](https://dauthau.asia)
và lưu về **JSON + SQLite** (kèm **ảnh và tệp đính kèm**), phục vụ tra cứu cho
SME và các mục đích nghiên cứu khác.

Dữ liệu thu về ở nhiều tầng để "không bỏ sót":
- **JSON có cấu trúc** cho từng bản ghi (tiêu đề, các trường khoá–giá trị, toàn văn, danh sách ảnh/đính kèm).
- **SQLite** (`data/dauthau.sqlite`) có full-text search để tra cứu/lọc nhanh.
- **HTML gốc** của mỗi trang (parse lại bất cứ lúc nào).
- **Ảnh + tệp đính kèm** tải về `data/<danh_mục>/assets/`.
- **XHR/JSON** bắt được khi trang gọi API ẩn (`data/<danh_mục>/xhr/`).

---

## 1. Cài đặt

Yêu cầu: **Python 3.9+**.

```bash
cd dauthau_crawler
pip install -r requirements.txt

# Trang render bằng JavaScript nên cần trình duyệt Chromium cho Playwright:
python -m playwright install chromium
```

## 2. Chạy thử nhanh (khuyến nghị làm trước tiên)

Chạy giới hạn nhỏ để kiểm tra hoạt động và tinh chỉnh trước khi crawl lớn:

```bash
# Xem các danh mục
python main.py --list

# Crawl thử 1 danh mục, 1 trang danh sách, tối đa 5 bản ghi, hiện trình duyệt để quan sát
python main.py --category van_ban_dau_thau --max-pages 1 --max-items 5 --show-browser
```

Sau khi chạy, xem kết quả:

```bash
python query.py --stats
python query.py --search "xây lắp"
python query.py --get <id_hiển_thị_ở_trên>
```

## 3. Crawl đầy đủ

```bash
# Tất cả danh mục đang bật trong config.py
python main.py

# Hoặc chọn danh mục cụ thể
python main.py -c thongbao_moithau -c ketqua_nhathau
```

Quá trình có thể **dừng và chạy lại bất cứ lúc nào** — tiến độ lưu ở
`data/_state.json`, các URL đã xong sẽ được bỏ qua (resume).

## 4. Các tham số dòng lệnh (`main.py`)

| Tham số | Ý nghĩa |
|---|---|
| `--category, -c KEY` | Chỉ crawl danh mục theo key (lặp lại được) |
| `--list` | Liệt kê danh mục |
| `--max-pages N` | Giới hạn số trang danh sách mỗi danh mục |
| `--max-items N` | Giới hạn số bản ghi mỗi danh mục |
| `--delay S` | Giây nghỉ giữa các request (mặc định 2s) |
| `--data-dir PATH` | Đổi thư mục lưu dữ liệu |
| `--no-assets` | Không tải ảnh/tệp đính kèm |
| `--show-browser` | Hiện cửa sổ trình duyệt (debug) |
| `--no-browser` | Dùng `requests` thay Playwright (chỉ hợp trang tĩnh) |

## 5. Tra cứu dữ liệu (`query.py`)

```bash
python query.py --stats                              # thống kê
python query.py --search "trạm y tế" --limit 20      # tìm toàn văn
python query.py --search "cầu" --category ketqua_nhathau
python query.py --get <id>                            # xem 1 bản ghi
python query.py --export-csv ketqua.csv --category ketqua_nhathau
```

Bạn cũng có thể mở trực tiếp `data/dauthau.sqlite` bằng DB Browser for SQLite,
hoặc đọc các file `data/<danh_mục>/json/*.json` và `*_all.ndjson`.

## 6. Cấu trúc thư mục dữ liệu

```
data/
├── dauthau.sqlite                 # CSDL tra cứu (mọi bản ghi + full-text)
├── crawl.log                      # nhật ký
├── _state.json                    # tiến độ (resume)
└── <danh_mục>/                    # vd: van_ban_dau_thau, thongbao_moithau...
    ├── json/<id>.json             # bản ghi có cấu trúc
    ├── html/<id>.html             # HTML gốc
    ├── xhr/<id>.json              # JSON/API bắt được (nếu có)
    ├── assets/<id>/images/...     # ảnh đã tải
    ├── assets/<id>/attachments/.. # tệp đính kèm đã tải
    └── <danh_mục>_all.ndjson      # gộp toàn bộ bản ghi (mỗi dòng 1 JSON)
```

Mỗi bản ghi JSON có dạng:

```json
{
  "id": "a1b2c3...",
  "url": "https://dauthau.asia/...",
  "category": "thongbao_moithau",
  "category_name": "Thông báo mời thầu (TBMT)",
  "title": "...",
  "fields": { "Số TBMT": "...", "Bên mời thầu": "...", "...": "..." },
  "text": "toàn văn nội dung...",
  "images": ["https://.../a.jpg"],
  "attachments": ["https://.../hsmt.pdf"],
  "downloaded_assets": { "images": [...], "attachments": [...] },
  "meta": { "description": "...", "og:title": "..." }
}
```

## 7. Tùy chỉnh (không cần sửa code lõi)

Mọi thứ điều khiển trong **`config.py`**:

- **Thêm/bớt danh mục**: sửa danh sách `CATEGORIES` (mỗi mục là một `list_url`).
- **Selector link chi tiết**: đặt `detail_link_sel` (CSS) nếu muốn chính xác hơn.
  Nếu để `None`, engine **tự dò** mọi link nằm sâu hơn trang danh sách và chứa
  `detail_url_contains` — nên vẫn chạy được ngay cả khi chưa tinh chỉnh.
- **Tốc độ / lịch sự**: `REQUEST_DELAY`, `RANDOM_JITTER`, `MAX_RETRIES`.
- **Tải ảnh/tệp**: `DOWNLOAD_ASSETS`, và `BLOCK_RESOURCES` (đừng chặn `image`
  nếu muốn ảnh hiển thị trong HTML lưu lại).
- **Định dạng lưu**: `SAVE_JSON`, `SAVE_SQLITE`, `SAVE_RAW_HTML`.

Parser (`crawler/parser.py`) trích xuất **tổng quát** (mọi bảng, danh sách,
ảnh, đính kèm) nên dữ liệu đầy đủ ngay cả khi giao diện thay đổi. Muốn map các
trường cho gọn theo từng danh mục, thêm hàm xử lý riêng trong `parse_detail`.

## 8. Lưu ý pháp lý & sử dụng có trách nhiệm

- Bộ mã này chỉ nhắm tới **dữ liệu công khai**, không đăng nhập, không vượt
  tường phí. Nhiều dữ liệu chi tiết trên dauthau.asia nằm sau tài khoản trả phí
  — công cụ này **không** truy cập phần đó.
- Hãy **đọc và tuân thủ Điều khoản sử dụng** của dauthau.asia
  (`/siteterms/terms-and-conditions.html`) và `robots.txt`. Mặc định crawler
  tôn trọng `robots.txt` (`RESPECT_ROBOTS_TXT = True`) và điều tiết tốc độ để
  không gây tải cho máy chủ.
- Dữ liệu gốc thường có nguồn từ Hệ thống mạng đấu thầu quốc gia; bạn nên kiểm
  chứng lại với nguồn chính thức trước khi dùng cho quyết định quan trọng.
- Dùng cho mục đích tra cứu/nghiên cứu; cân nhắc bản quyền khi tái phân phối.

## 9. Kiến trúc mã nguồn

```
dauthau_crawler/
├── main.py                 # CLI chạy crawl
├── query.py                # CLI tra cứu dữ liệu đã crawl
├── config.py               # TẤT CẢ cấu hình (sửa ở đây)
├── requirements.txt
└── crawler/
    ├── config_bridge.py    # gom config -> Settings (ghi đè bằng CLI)
    ├── fetcher.py          # Playwright + requests, robots, rate limit, retry, bắt XHR
    ├── parser.py           # trích xuất field/ảnh/đính kèm/link (BeautifulSoup)
    ├── storage.py          # lưu JSON + SQLite (+FTS) + resume state
    ├── assets.py           # tải ảnh & tệp đính kèm
    ├── engine.py           # điều phối list -> detail -> lưu
    └── utils.py            # logging, URL, slug, hashing
```
