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
def login_interactive(platform: str, login_url: str) -> bool:
    """headed 模式打开浏览器，等待用户手动登录，保存 cookie。"""
    if not playwright_available():
        print("playwright 未安装，无法执行登录引导。")
        print("请先: pip install playwright && playwright install chromium")
        return False
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    launch_kwargs: dict[str, Any] = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    exe = _find_chrome_executable()
    if exe:
        launch_kwargs["executable_path"] = exe
    browser = pw.chromium.launch(**launch_kwargs)
    try:
        context = browser.new_context()
        page = context.new_page()
        print(f"\n【登录引导】正在打开 {platform} 登录页...")
        print(f"请在弹出的浏览器窗口中完成登录，登录后回到本终端按回车保存 cookie。\n")
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        input("登录完成后，请在此处按回车 → ")
        # 保存 cookie + localStorage
        cookie_file = _cookie_path(platform)
        state = context.storage_state()
        cookie_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print(f"✓ cookie 已保存到 {cookie_file}")
        return True
    finally:
        browser.close()
        pw.stop()


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
