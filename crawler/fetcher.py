# -*- coding: utf-8 -*-
"""
fetcher.py — Lấy nội dung trang.

Hai chế độ:
  * BrowserFetcher  : dùng Playwright (Chromium headless) để render JavaScript.
                      Đây là chế độ mặc định vì dauthau.asia render bằng JS.
                      Đồng thời chặn (capture) mọi phản hồi JSON/XHR — nếu trang
                      gọi API ẩn, ta lưu luôn dữ liệu gốc đó.
  * SimpleFetcher   : dùng requests (nhanh, nhẹ) cho các trang tĩnh (robots.txt,
                      tải ảnh/tệp đính kèm).

Cả hai đều: tôn trọng robots.txt, điều tiết tốc độ (rate limit), retry.
"""

from __future__ import annotations
import random
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

from . import config_bridge as C
from .utils import get_logger, load_netscape_cookies

log = get_logger()


def _load_cookies(settings: "C.Settings") -> list[dict]:
    """Đọc cookies.txt nếu bật USE_COOKIES. Trả về [] nếu không có."""
    if not getattr(settings, "use_cookies", False):
        return []
    cookies = load_netscape_cookies(getattr(settings, "cookies_file", ""))
    if cookies:
        log.info("Đã nạp %d cookies từ %s (đăng nhập lại phiên cũ).",
                len(cookies), settings.cookies_file)
    else:
        log.warning("USE_COOKIES=True nhưng không đọc được cookie nào từ %s.",
                    getattr(settings, "cookies_file", ""))
    return cookies


# Dấu hiệu trong HTML cho biết ĐÃ đăng nhập (link đăng xuất / trang tài khoản).
_LOGIN_MARKERS = ("users/logout", "/users/editinfo", "Thoát", "Đăng xuất")
# Dấu hiệu CHƯA đăng nhập.
_LOGOUT_MARKERS = ("users/login", "Đăng nhập")


def check_login(fetcher, settings: "C.Settings") -> bool:
    """Tải trang chủ và đoán trạng thái đăng nhập dựa trên HTML."""
    res = fetcher.get(settings.base_url + "/")
    if not res.ok:
        log.warning("Không kiểm tra được đăng nhập (lỗi tải trang chủ: %s).", res.error)
        return False
    html = res.html or ""
    logged_in = any(m in html for m in _LOGIN_MARKERS)
    if logged_in:
        log.info("✔ ĐÃ ĐĂNG NHẬP bằng cookies — dữ liệu chi tiết sẽ đầy đủ hơn.")
    else:
        log.warning("✗ CHƯA đăng nhập (cookies có thể đã hết hạn). "
                    "Hãy đăng nhập lại trên trình duyệt rồi xuất cookies.txt mới.")
    return logged_in


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    html: str = ""
    ok: bool = False
    xhr_json: list = field(default_factory=list)   # các payload JSON bắt được
    error: str | None = None


class RateLimiter:
    """Đảm bảo khoảng nghỉ tối thiểu giữa các request để lịch sự với máy chủ."""

    def __init__(self, delay: float, jitter: float = 0.0):
        self.delay = delay
        self.jitter = jitter
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        gap = now - self._last
        need = self.delay + random.uniform(0, self.jitter)
        if gap < need:
            time.sleep(need - gap)
        self._last = time.monotonic()


class RobotsGate:
    """Đọc và kiểm tra robots.txt (cache theo domain)."""

    def __init__(self, base_url: str, user_agent: str, enabled: bool = True):
        self.enabled = enabled
        self.user_agent = user_agent
        self._parsers: dict[str, robotparser.RobotFileParser] = {}
        self.base_url = base_url

    def _parser_for(self, url: str) -> robotparser.RobotFileParser | None:
        if not self.enabled:
            return None
        netloc = urlparse(url).netloc
        if netloc not in self._parsers:
            rp = robotparser.RobotFileParser()
            robots_url = f"{urlparse(url).scheme}://{netloc}/robots.txt"
            try:
                resp = requests.get(robots_url, timeout=15,
                                    headers={"User-Agent": self.user_agent})
                if resp.status_code == 200 and resp.text.strip():
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])  # rỗng => cho phép tất cả
                log.info("Đã đọc robots.txt từ %s (status %s)", robots_url, resp.status_code)
            except Exception as e:  # noqa
                log.warning("Không đọc được robots.txt (%s) — mặc định cho phép.", e)
                rp.parse([])
            self._parsers[netloc] = rp
        return self._parsers[netloc]

    def allowed(self, url: str) -> bool:
        rp = self._parser_for(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True


class SimpleFetcher:
    """Fetcher dựa trên requests — cho trang tĩnh và tải tệp."""

    def __init__(self, settings: "C.Settings"):
        self.s = settings
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent,
                                    "Accept-Language": "vi,en;q=0.8"})
        # Nạp cookies đăng nhập (nếu có) vào session.
        for ck in _load_cookies(settings):
            self.session.cookies.set(
                ck["name"], ck["value"],
                domain=ck["domain"], path=ck["path"],
                secure=ck["secure"],
            )
        self.limiter = RateLimiter(settings.request_delay, settings.random_jitter)
        self.robots = RobotsGate(settings.base_url, settings.user_agent,
                                settings.respect_robots)

    def get(self, url: str) -> FetchResult:
        if not self.robots.allowed(url):
            log.warning("robots.txt CHẶN: %s", url)
            return FetchResult(url, url, 0, ok=False, error="blocked_by_robots")
        self.limiter.wait()
        last_err = None
        for attempt in range(1, self.s.max_retries + 1):
            try:
                r = self.session.get(url, timeout=self.s.page_timeout / 1000)
                return FetchResult(url, r.url, r.status_code, r.text,
                                    ok=r.ok, error=None if r.ok else f"HTTP {r.status_code}")
            except Exception as e:  # noqa
                last_err = str(e)
                log.warning("Lỗi tải %s (lần %d): %s", url, attempt, e)
                time.sleep(self.s.retry_backoff * attempt)
        return FetchResult(url, url, 0, ok=False, error=last_err)

    def download(self, url: str, dest_path: str) -> bool:
        """Tải file nhị phân (ảnh, pdf, doc...) về dest_path."""
        if not self.robots.allowed(url):
            log.warning("robots.txt CHẶN tệp: %s", url)
            return False
        self.limiter.wait()
        for attempt in range(1, self.s.max_retries + 1):
            try:
                with self.session.get(url, timeout=self.s.page_timeout / 1000,
                                    stream=True) as r:
                    if not r.ok:
                        return False
                    with open(dest_path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            f.write(chunk)
                return True
            except Exception as e:  # noqa
                log.warning("Lỗi tải tệp %s (lần %d): %s", url, attempt, e)
                time.sleep(self.s.retry_backoff * attempt)
        return False


class BrowserFetcher:
    """Fetcher dùng Playwright — render JS, bắt XHR JSON."""

    def __init__(self, settings: "C.Settings"):
        self.s = settings
        self.limiter = RateLimiter(settings.request_delay, settings.random_jitter)
        self.robots = RobotsGate(settings.base_url, settings.user_agent,
                                settings.respect_robots)
        self._pw = None
        self._browser = None
        self._context = None

    # -- vòng đời -----------------------------------------------------------
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()

    def start(self):
        from playwright.sync_api import sync_playwright  # import trễ
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.s.headless)
        self._context = self._browser.new_context(
            user_agent=self.s.user_agent,
            locale="vi-VN",
            viewport={"width": 1366, "height": 900},
        )
        # Nạp cookies đăng nhập (nếu có) vào browser context.
        cookies = _load_cookies(self.s)
        if cookies:
            pw_cookies = []
            for ck in cookies:
                c = {
                    "name": ck["name"],
                    "value": ck["value"],
                    "domain": ck["domain"],
                    "path": ck["path"],
                    "secure": ck["secure"],
                    "httpOnly": ck.get("httpOnly", False),
                }
                # expires=0 (cookie phiên) => Playwright dùng -1
                c["expires"] = ck["expires"] if ck["expires"] > 0 else -1
                pw_cookies.append(c)
            try:
                self._context.add_cookies(pw_cookies)
                log.info("Đã gắn %d cookies vào trình duyệt.", len(pw_cookies))
            except Exception as e:  # noqa
                log.warning("Không gắn được cookies vào trình duyệt: %s", e)
        # Chặn tải tài nguyên không cần thiết để nhanh hơn.
        block = set(self.s.block_resources or [])
        if block:
            def _route(route):
                if route.request.resource_type in block:
                    return route.abort()
                return route.continue_()
            self._context.route("**/*", _route)
        log.info("Đã khởi động trình duyệt (headless=%s).", self.s.headless)

    def close(self):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # -- lấy trang ----------------------------------------------------------
    def get(self, url: str) -> FetchResult:
        if not self.robots.allowed(url):
            log.warning("robots.txt CHẶN: %s", url)
            return FetchResult(url, url, 0, ok=False, error="blocked_by_robots")
        self.limiter.wait()

        last_err = None
        for attempt in range(1, self.s.max_retries + 1):
            page = self._context.new_page()
            captured: list = []

            if self.s.capture_xhr_json:
                def _on_response(resp):
                    try:
                        ct = (resp.headers or {}).get("content-type", "")
                        if "application/json" in ct:
                            captured.append({"url": resp.url,
                                            "json": resp.json()})
                    except Exception:
                        pass
                page.on("response", _on_response)

            try:
                resp = page.goto(url, wait_until=self.s.nav_wait_until,
                                timeout=self.s.page_timeout)
                # Cuộn xuống để kích hoạt lazy-load nếu có.
                try:
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                html = page.content()
                status = resp.status if resp else 200
                final = page.url
                page.close()
                return FetchResult(url, final, status, html,
                                    ok=(status < 400), xhr_json=captured,
                                    error=None if status < 400 else f"HTTP {status}")
            except Exception as e:  # noqa
                last_err = str(e)
                log.warning("Lỗi render %s (lần %d): %s", url, attempt, e)
                try:
                    page.close()
                except Exception:
                    pass
                time.sleep(self.s.retry_backoff * attempt)
        return FetchResult(url, url, 0, ok=False, error=last_err)


def make_fetcher(settings: "C.Settings"):
    """Trả về fetcher phù hợp theo cấu hình."""
    if settings.use_browser:
        return BrowserFetcher(settings)
    return SimpleFetcher(settings)
