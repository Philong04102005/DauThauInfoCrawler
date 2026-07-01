# -*- coding: utf-8 -*-
"""
query.py — Công cụ tra cứu nhanh dữ liệu đã crawl (đọc từ SQLite).

Đây là ví dụ minh hoạ "người dùng có thể lấy data từ cái đã crawl về".

Ví dụ:
  python query.py --stats                       # thống kê số bản ghi mỗi danh mục
  python query.py --search "xây lắp"            # tìm toàn văn theo từ khoá
  python query.py --search "trạm y tế" --category thongbao_moithau --limit 20
  python query.py --get <id>                     # xem 1 bản ghi (JSON)
  python query.py --export-csv ketqua.csv --category ketqua_nhathau
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as user_config


def connect():
    if not os.path.exists(user_config.SQLITE_FILE):
        print(f"Chưa có CSDL: {user_config.SQLITE_FILE}. Hãy chạy main.py trước.")
        sys.exit(1)
    con = sqlite3.connect(user_config.SQLITE_FILE)
    con.row_factory = sqlite3.Row
    return con


def cmd_stats(con):
    print("Số bản ghi theo danh mục:")
    for row in con.execute(
        "SELECT category, COUNT(*) n FROM records GROUP BY category ORDER BY n DESC"):
        print(f"  {row['category']:<24} {row['n']:>8}")
    total = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    print(f"  {'TỔNG':<24} {total:>8}")


def cmd_search(con, term, category, limit):
    # Ưu tiên FTS nếu có, ngược lại LIKE.
    rows = []
    try:
        q = ("SELECT r.id, r.category, r.title, r.url FROM records_fts f "
            "JOIN records r ON r.id=f.id WHERE records_fts MATCH ? ")
        params = [term]
        if category:
            q += "AND r.category=? "
            params.append(category)
        q += "LIMIT ?"
        params.append(limit)
        rows = con.execute(q, params).fetchall()
    except sqlite3.OperationalError:
        pass
    if not rows:
        q = ("SELECT id, category, title, url FROM records "
            "WHERE (title LIKE ? OR text LIKE ?) ")
        params = [f"%{term}%", f"%{term}%"]
        if category:
            q += "AND category=? "
            params.append(category)
        q += "LIMIT ?"
        params.append(limit)
        rows = con.execute(q, params).fetchall()

    print(f"Tìm '{term}' — {len(rows)} kết quả:\n")
    for r in rows:
        print(f"[{r['category']}] {r['title']}")
        print(f"   id={r['id']}  {r['url']}\n")


def cmd_get(con, rec_id):
    row = con.execute("SELECT * FROM records WHERE id=?", (rec_id,)).fetchone()
    if not row:
        print("Không tìm thấy id.")
        return
    obj = dict(row)
    for k in ("fields_json", "images_json", "attachments_json", "meta_json"):
        try:
            obj[k] = json.loads(obj[k])
        except Exception:
            pass
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_export_csv(con, path, category):
    q = "SELECT id, category, title, url, crawled_at FROM records"
    params = []
    if category:
        q += " WHERE category=?"
        params.append(category)
    rows = con.execute(q, params).fetchall()
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "title", "url", "crawled_at"])
        for r in rows:
            w.writerow([r["id"], r["category"], r["title"], r["url"], r["crawled_at"]])
    print(f"Đã xuất {len(rows)} dòng -> {path}")


def main():
    p = argparse.ArgumentParser(description="Tra cứu dữ liệu dauthau đã crawl.")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--search")
    p.add_argument("--category")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--get")
    p.add_argument("--export-csv")
    args = p.parse_args()

    con = connect()
    if args.stats:
        cmd_stats(con)
    elif args.search:
        cmd_search(con, args.search, args.category, args.limit)
    elif args.get:
        cmd_get(con, args.get)
    elif args.export_csv:
        cmd_export_csv(con, args.export_csv, args.category)
    else:
        cmd_stats(con)
    con.close()


if __name__ == "__main__":
    main()
