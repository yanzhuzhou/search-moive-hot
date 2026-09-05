"""Playwright 浏览器管理器 + 三平台采集器。

设计：
- 共享 BrowserManager 管理浏览器生命周期（复用实例，减少启动开销）
- 每个平台一个采集器，继承 BaseScraper
- 首次运行：headed 模式打开，让用户手动登录，登录后存 cookie 到 .playwright_cookies/<platform>.json
- 后续运行：headless 模式加载 cookie 直接爬
- Playwright 不可用时自动抛 ScrapeError → 上层回退演示数据
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ..models import Product
from .base import BaseScraper, ScrapeError

log = logging.getLogger("price_compare.scrapers.playwright")

COOKIE_DIR = Path(__file__).resolve().parent.parent.parent / ".playwright_cookies"


def _find_chrome_executable() -> str | None:
    """查找可用的 Chrome/Chromium 可执行文件。

    优先顺序：环境变量 → puppeteer 缓存 → 系统安装 → playwright 默认。
    """
    env_path = os.environ.get("PRICE_COMPARE_CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        Path.home() / ".cache/puppeteer/chrome",
        Path.home() / ".cache/ms-playwright",
    ]
    for base in candidates:
        if not base.exists():
            continue
        for exe in base.rglob("chrome"):
            if exe.is_file() and os.access(exe, os.X_OK):
                return str(exe)

    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        p = shutil_which(name)
        if p:
            return p
    return None


def shutil_which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


def _ensure_dir() -> Path:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    return COOKIE_DIR


def _cookie_path(name: str) -> Path:
    return _ensure_dir() / f"{name}.json"


def playwright_available() -> bool:
    """检查 playwright 是否可导入（不尝试启动浏览器）。"""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# ---- 浏览器生命周期管理 ---------------------------------------------
_browser_instance = None
_browser_type = None


def _get_browser():
    """全局复用的浏览器实例。"""
    global _browser_instance, _browser_type
    if _browser_instance is not None:
        return _browser_instance
    if not playwright_available():
        raise ScrapeError("playwright 未安装，请先 pip install playwright && playwright install chromium")
    try:
        from playwright.sync_api import sync_playwright
        _browser_type = sync_playwright().start()
        exe = _find_chrome_executable()
        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        }
        if exe:
            launch_kwargs["executable_path"] = exe
            log.debug("使用 Chrome: %s", exe)
        _browser_instance = _browser_type.chromium.launch(**launch_kwargs)
        return _browser_instance
    except Exception as e:  # noqa: BLE001
        raise ScrapeError(f"浏览器启动失败: {e}") from e


def close_browser() -> None:
    """关闭浏览器进程（程序退出时调用）。"""
    global _browser_instance, _browser_type
    if _browser_instance is not None:
        try:
            _browser_instance.close()
        except Exception:  # noqa: BLE001
            pass
        _browser_instance = None
    if _browser_type is not None:
        try:
            _browser_type.stop()
        except Exception:  # noqa: BLE001
            pass
        _browser_type = None


# ---- 登录辅助 -------------------------------------------------------
# 各平台登录成功检测条件：URL 不再是登录页 + cookie 中出现登录态字段
_LOGIN_DETECT = {
    "jd": {
        "login_host": "passport.jd.com",
        "cookie_keys": ("pt_key", "pt_pin"),
    },
    "taobao": {
        "login_host": "login.taobao.com",
        "cookie_keys": ("logincookie", "_m_h5_tk", "unb"),
    },
    "pinduoduo": {
        "login_host": "mobile.yangkeduo.com/login",
        "cookie_keys": ("PASS_ID", "pdd_user_id"),
    },
}


def _detect_login_success(context: Any, platform: str) -> bool:
    """检测是否已登录成功：cookie 中出现登录态字段。"""
    cfg = _LOGIN_DETECT.get(platform, {})
    cookie_keys = cfg.get("cookie_keys", [])
    if not cookie_keys:
        return False
    cookies = context.cookies()
    cookie_names = {c.get("name", "") for c in cookies}
    return any(k in cookie_names for k in cookie_keys)


def login_interactive(platform: str, login_url: str, timeout: int = 300) -> dict:
    """在虚拟显示器上 headed 模式打开浏览器，轮询检测登录成功后自动保存 cookie。

    非交互式设计（沙箱无 TTY）：不等待 input()，而是轮询 cookie 检测登录态。
    用户通过 noVNC 网页操作浏览器完成登录。

    Args:
        platform: "jd" / "taobao" / "pinduoduo"
        login_url: 登录页 URL
        timeout: 最长等待秒数（默认 300）
    Returns:
        {"success": bool, "elapsed": float, "cookie_file": str, "error": str}
    """
    result = {"success": False, "elapsed": 0, "cookie_file": "", "error": ""}
    if not playwright_available():
        result["error"] = "playwright 未安装"
        return result
    import time
    from playwright.sync_api import sync_playwright
    start = time.time()
    pw = sync_playwright().start()
    launch_kwargs: dict[str, Any] = {
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--start-maximized",
        ],
    }
    exe = _find_chrome_executable()
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        log.info("[login] 打开 %s 登录页: %s", platform, login_url)
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        # 轮询检测登录成功
        while time.time() - start < timeout:
            time.sleep(3)
            if _detect_login_success(context, platform):
                elapsed = round(time.time() - start, 1)
                cookie_file = _cookie_path(platform)
                state = context.storage_state()
                cookie_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                log.info("[login] ✓ %s 登录成功，cookie 已保存 (%.1fs)", platform, elapsed)
                result.update(success=True, elapsed=elapsed, cookie_file=str(cookie_file))
                break
        else:
            result["error"] = f"等待 {timeout}s 超时，未检测到登录成功"
            log.warning("[login] %s 登录超时", platform)
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
        log.error("[login] 异常: %s", e)
    finally:
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            pass
        pw.stop()
    return result


def _load_context(browser, platform: str):
    """带 cookie 创建 context。"""
    state_file = _cookie_path(platform)
    if state_file.exists():
        return browser.new_context(storage_state=str(state_file))
    # 无 cookie，空 context
    return browser.new_context()


# ---- 各平台 Playwright 采集器 ----------------------------------------
class _PlaywrightMixin:
    """混入类：把 Playwright 能力注入 BaseScraper 子类。"""
    platform_key: str = ""          # "jd" / "taobao" / "pinduoduo"
    login_url: str = ""

    def _fetch(self, keyword: str, limit: int) -> list[Product]:  # noqa: D401
        """由 BaseScraper.search 调用，子类只需实现 _parse_page。"""
        browser = _get_browser()
        context = _load_context(browser, self.platform_key)
        page = context.new_page()
        try:
            url = self._search_url(keyword)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # 等待商品卡片出现
            self._wait_for_cards(page)
            # 滚动加载更多
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(800)
            items = self._parse_page(page, keyword, limit)
            if not items:
                raise ScrapeError("Playwright 未解析到商品（可能被反爬拦截，尝试手动登录一次）")
            return items
        except ScrapeError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ScrapeError(f"Playwright 采集异常: {e}") from e
        finally:
            page.close()
            context.close()

    def _search_url(self, keyword: str) -> str:
        raise NotImplementedError

    def _wait_for_cards(self, page) -> None:
        raise NotImplementedError

    def _parse_page(self, page, keyword: str, limit: int) -> list[Product]:
        raise NotImplementedError


class PlaywrightJDScraper(_PlaywrightMixin, BaseScraper):
    """京东 Playwright 采集器。"""
    name = "jd_pw"
    platform_cn = "京东"
    platform_key = "jd"
    login_url = "https://passport.jd.com/new/login.aspx"

    def _search_url(self, keyword: str) -> str:
        return f"https://search.jd.com/Search?keyword={urllib.parse.quote(keyword)}&enc=utf-8"

    def _wait_for_cards(self, page) -> None:
        try:
            page.wait_for_selector("li.gl-item", timeout=8000)
        except Exception:
            page.wait_for_load_state("networkidle", timeout=8000)

    def _parse_page(self, page, keyword: str, limit: int) -> list[Product]:
        # 用 evaluate 一次性抽 DOM，比逐个 locator 快
        items_js = page.evaluate("""
        () => {
            const results = [];
            const nodes = document.querySelectorAll('li.gl-item');
            nodes.forEach(li => {
                const sku = li.getAttribute('data-sku') || '';
                const titleEl = li.querySelector('.p-name em');
                const priceEl = li.querySelector('.p-price i');
                const shopEl = li.querySelector('.p-shop a');
                results.push({
                    sku,
                    title: titleEl ? titleEl.innerText.trim() : '',
                    price: priceEl ? priceEl.innerText.trim() : '0',
                    shop: shopEl ? shopEl.innerText.trim() : '京东自营',
                    url: sku ? `https://item.jd.com/${sku}.html` : '',
                });
            });
            return results;
        }""")
        products = []
        for raw in items_js[:limit]:
            try:
                price = float(raw["price"].replace(",", "").replace("¥", "") or "0")
            except ValueError:
                price = 0.0
            if price <= 0:
                continue
            products.append(Product(
                platform="京东", title=raw["title"], price=price,
                sales=0, shop=raw["shop"], shop_rating=4.8,
                url=raw["url"] or self._search_url(keyword),
                sku_id=raw["sku"], source="real",
            ))
        return products


class PlaywrightTaobaoScraper(_PlaywrightMixin, BaseScraper):
    """淘宝 Playwright 采集器。"""
    name = "taobao_pw"
    platform_cn = "淘宝"
    platform_key = "taobao"
    login_url = "https://login.taobao.com/member/login.htm"

    def _search_url(self, keyword: str) -> str:
        return f"https://s.taobao.com/search?q={urllib.parse.quote(keyword)}"

    def _wait_for_cards(self, page) -> None:
        # 淘宝用 App 组件渲染，等商品卡片出现
        try:
            page.wait_for_selector("[data-item-id], .ContentItem--MainItem", timeout=10000)
        except Exception:
            page.wait_for_load_state("networkidle", timeout=10000)

    def _parse_page(self, page, keyword: str, limit: int) -> list[Product]:
        # 淘宝新旧版结构差异大，用多重选择器兜底
        items_js = page.evaluate("""
        () => {
            const results = [];
            // 新版：ContentItem
            document.querySelectorAll('.ContentItem--MainItem, [class*="Card--doubleCard"]')
                .forEach(card => {
                    const titleEl = card.querySelector('.Title--title, [class*="title"] span, img[alt]');
                    const priceEl = card.querySelector('.Price--priceInt, [class*="priceInt"]');
                    const shopEl = card.querySelector('.ShopInfo--shopName, [class*="shopName"]');
                    const itemId = card.getAttribute('data-item-id') || '';
                    const title = titleEl ? (titleEl.innerText.trim() || titleEl.getAttribute('alt') || '') : '';
                    const priceText = priceEl ? priceEl.innerText.trim() : '';
                    results.push({
                        sku: itemId, title, price: priceText,
                        shop: shopEl ? shopEl.innerText.trim() : '淘宝店铺',
                        url: itemId ? `https://item.taobao.com/item.htm?id=${itemId}` : '',
                    });
                });
            return results;
        }""")
        products = []
        for raw in items_js[:limit]:
            try:
                price = float("".join(c for c in raw["price"] if c.isdigit() or c == "."))
            except ValueError:
                price = 0.0
            if price <= 0 or not raw["title"]:
                continue
            products.append(Product(
                platform="淘宝", title=raw["title"], price=price,
                sales=0, shop=raw["shop"], shop_rating=4.7,
                url=raw["url"] or self._search_url(keyword),
                sku_id=raw["sku"], source="real",
            ))
        return products


class PlaywrightPinduoduoScraper(_PlaywrightMixin, BaseScraper):
    """拼多多 Playwright 采集器（用 PC 网页版 yangkeduo.com）。"""
    name = "pinduoduo_pw"
    platform_cn = "拼多多"
    platform_key = "pinduoduo"
    login_url = "https://mobile.yangkeduo.com/login.html"

    def _search_url(self, keyword: str) -> str:
        return f"https://mobile.yangkeduo.com/search_result.html?search_key={urllib.parse.quote(keyword)}"

    def _wait_for_cards(self, page) -> None:
        try:
            page.wait_for_selector('[class*="goods-item"], .search-result-item', timeout=10000)
        except Exception:
            page.wait_for_load_state("networkidle", timeout=10000)

    def _parse_page(self, page, keyword: str, limit: int) -> list[Product]:
        items_js = page.evaluate("""
        () => {
            const results = [];
            document.querySelectorAll('[class*="goods-item"], [class*="ItemWrapper"], .search-result-item')
                .forEach(card => {
                    const titleEl = card.querySelector('[class*="title"], [class*="Title"]');
                    const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                    const goodsId = card.getAttribute('data-goods-id') || card.getAttribute('goods_id') || '';
                    results.push({
                        sku: goodsId,
                        title: titleEl ? titleEl.innerText.trim() : '',
                        price: priceEl ? priceEl.innerText.trim() : '',
                        url: goodsId ? `https://mobile.yangkeduo.com/goods.html?goods_id=${goodsId}` : '',
                    });
                });
            return results;
        }""")
        products = []
        for raw in items_js[:limit]:
            try:
                price = float("".join(c for c in raw["price"] if c.isdigit() or c == "."))
            except ValueError:
                price = 0.0
            if price <= 0 or not raw["title"]:
                continue
            products.append(Product(
                platform="拼多多", title=raw["title"], price=price,
                sales=0, shop="拼多多店铺", shop_rating=4.5,
                url=raw["url"] or self._search_url(keyword),
                sku_id=raw["sku"], source="real",
            ))
        return products
