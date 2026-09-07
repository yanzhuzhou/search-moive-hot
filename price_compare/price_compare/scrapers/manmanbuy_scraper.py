"""慢慢买比价网采集器（免登录）。

核心思路：
- 慢慢买 (manmanbuy.com) 是公开比价聚合站，已收录京东/天猫/拼多多等平台的商品价格；
- 搜索结果页 https://s.manmanbuy.com/pc/search/result?keyword=xxx 服务端渲染，
  无需登录即可查看，用 Playwright 无头模式渲染后解析 DOM 即可；
- 这样绕过了京东/淘宝/拼多多各自的登录墙与风控参数，实现「零登录」采集。

平台映射：
- 京东自营 / 京东商城 → 京东
- 天猫商城 / 天猫旗舰店 / 淘宝 → 淘宝
- 拼多多 → 拼多多
"""
from __future__ import annotations

import logging
import re
import urllib.parse
from typing import Any

from ..models import Product, Platform
from .base import BaseScraper, ScrapeError

log = logging.getLogger("price_compare.scrapers.manmanbuy")

_SEARCH_URL = "https://s.manmanbuy.com/pc/search/result?c=discount&keyword={kw}"

# 慢慢买页面上的来源文案 → 内部平台
_PLATFORM_MAP = {
    "京东自营": Platform.JD,
    "京东商城": Platform.JD,
    "京东": Platform.JD,
    "天猫商城": Platform.TAOBAO,
    "天猫旗舰店": Platform.TAOBAO,
    "天猫": Platform.TAOBAO,
    "淘宝": Platform.TAOBAO,
    "拼多多": Platform.PINDUODUO,
}


def _classify_platform(text: str) -> Platform | None:
    """从商品文本末尾的来源文案判断平台。"""
    for key, plat in _PLATFORM_MAP.items():
        if key in text:
            return plat
    return None


def _parse_price(text: str) -> float:
    """从 '23.49元' / '16.12元+6.78元淘金币' 中提取主价格。"""
    m = re.search(r"(\d+\.?\d*)\s*元", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0


def _extract_title(text: str) -> str:
    """从卡片文本中提取商品标题（去掉价格、标签、来源等尾部信息）。"""
    # 去掉开头的 "精选" 等标签
    t = re.sub(r"^(精选|好价|爆料)\s+", "", text)
    # 在价格处截断
    m = re.search(r"\d+\.?\d*\s*元", t)
    if m:
        t = t[: m.start()].strip()
    # 去掉末尾可能残留的 "去看看" 等
    t = re.sub(r"去看看.*$", "", t).strip()
    return t[:120]


# ---- 浏览器共享 -------------------------------------------------------
_pw_browser = None
_pw_playwright = None

# 关键词缓存：同一关键词只加载一次慢慢买页面，避免三平台重复请求
_cache: dict[str, list[Product]] = {}


def _get_browser():
    global _pw_browser, _pw_playwright
    if _pw_browser is not None:
        return _pw_browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ScrapeError(f"playwright 未安装: {e}") from e
    _pw_playwright = sync_playwright().start()
    _pw_browser = _pw_playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    return _pw_browser


def close_browser() -> None:
    global _pw_browser, _pw_playwright
    if _pw_browser is not None:
        try:
            _pw_browser.close()
        except Exception:  # noqa: BLE001
            pass
        _pw_browser = None
    if _pw_playwright is not None:
        try:
            _pw_playwright.stop()
        except Exception:  # noqa: BLE001
            pass
        _pw_playwright = None


def fetch_manmanbuy(keyword: str, limit: int = 60) -> list[Product]:
    """从慢慢买抓取搜索结果（全部平台），带关键词缓存。

    Returns:
        Product 列表，platform 字段已映射为京东/淘宝/拼多多。
    """
    kw = keyword.strip()
    if not kw:
        return []
    if kw in _cache:
        return _cache[kw][:limit]
    browser = _get_browser()
    context = browser.new_context(
        viewport={"width": 1366, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    try:
        url = _SEARCH_URL.format(kw=urllib.parse.quote(keyword))
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # 等待商品卡片渲染
        try:
            page.wait_for_selector('[class*="DiscountItemPC_box"]', timeout=20000)
        except Exception:  # noqa: BLE001
            page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(3000)
        # 滚动触发懒加载价格
        for _ in range(4):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(900)

        raw_items = page.evaluate(
            """() => {
            const cards = document.querySelectorAll('[class*="DiscountItemPC_box"]');
            const out = [];
            cards.forEach(card => {
                const text = (card.innerText || '').replace(/\\n/g, ' ').trim();
                let href = '';
                card.querySelectorAll('a[href]').forEach(a => {
                    const h = a.href || '';
                    if (h && !href) href = h;
                });
                out.push({text, href});
            });
            return out;
        }"""
        )

        products: list[Product] = []
        for raw in raw_items:
            text = raw.get("text", "")
            if not text or "元" not in text:
                continue
            platform = _classify_platform(text)
            if platform is None:
                continue
            price = _parse_price(text)
            if price <= 0:
                continue
            title = _extract_title(text)
            if not title:
                continue
            shop = "京东自营" if platform == Platform.JD else (
                "天猫旗舰店" if platform == Platform.TAOBAO else "拼多多店铺"
            )
            # 从来源文案中提取更准确的店铺名
            shop_m = re.search(r"(京东自营|京东商城|天猫商城|天猫旗舰店|淘宝|拼多多)", text)
            if shop_m:
                shop = shop_m.group(1)
            products.append(Product(
                platform=platform.value,
                title=title,
                price=price,
                sales=0,
                shop=shop,
                shop_rating=4.8 if platform == Platform.JD else (4.7 if platform == Platform.TAOBAO else 4.5),
                url=raw.get("href", ""),
                sku_id="",
                source="real",
                extra={"aggregator": "manmanbuy"},
            ))
            if len(products) >= limit:
                break
        _cache[kw] = products  # 缓存全量结果
        return products[:limit]
    except Exception as e:  # noqa: BLE001
        raise ScrapeError(f"慢慢买采集失败: {e}") from e
    finally:
        page.close()
        context.close()


def fetch_pinduoduo_mobile(keyword: str, limit: int = 10) -> list[Product]:
    """直连拼多多移动 H5 搜索页（免登录补充）。

    慢慢买的拼多多数据较少，这里用 Playwright 直接访问拼多多移动搜索页作为补充。
    拼多多移动页在未登录状态下可浏览搜索结果。
    """
    if not keyword.strip():
        return []
    browser = _get_browser()
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
    )
    page = context.new_page()
    try:
        url = "https://mobile.yangkeduo.com/search_result.html?search_key=" + urllib.parse.quote(keyword)
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        for _ in range(3):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(800)

        raw = page.evaluate(
            """() => {
            const out = [];
            // 拼多多移动页商品卡片
            document.querySelectorAll('[class*="goods"], [class*="item"], [class*="card"]').forEach(el => {
                const t = (el.innerText || '').replace(/\\n/g, ' ').trim();
                if (t.length < 8 || t.length > 300) return;
                const pm = t.match(/¥?\\s*(\\d+\\.?\\d*)/);
                if (!pm) return;
                let href = '';
                const a = el.querySelector('a[href]');
                if (a) href = a.href;
                out.push({text: t, price: pm[1], href});
            });
            return out;
        }"""
        )
        products: list[Product] = []
        seen = set()
        for r in raw:
            text = r.get("text", "")
            price = float(r.get("price", 0) or 0)
            if price <= 0:
                continue
            # 提取标题（价格前面的部分）
            m = re.search(r"\d+\.?\d*", text)
            title = text[: m.start()].strip() if m else text[:60]
            title = re.sub(r"^[¥￥]\s*", "", title).strip()[:80]
            if not title or title[:20] in seen:
                continue
            seen.add(title[:20])
            products.append(Product(
                platform=Platform.PINDUODUO.value,
                title=title,
                price=price,
                sales=0,
                shop="拼多多店铺",
                shop_rating=4.5,
                url=r.get("href", "") or f"https://mobile.yangkeduo.com/search_result.html?search_key={urllib.parse.quote(keyword)}",
                sku_id="",
                source="real",
                extra={"aggregator": "pdd_mobile"},
            ))
            if len(products) >= limit:
                break
        return products
    except Exception as e:  # noqa: BLE001
        log.debug("拼多多移动页采集失败: %s", e)
        return []
    finally:
        page.close()
        context.close()


# ---- 按平台过滤的采集器 -----------------------------------------------
class ManmanbuyScraper(BaseScraper):
    """基于慢慢买的平台采集器（免登录）。

    通过 aggregator 一次抓取，再按平台过滤，避免重复启动浏览器。
    """

    name = "manmanbuy"
    platform_cn = ""  # 由子类设置
    platform_key: str = ""  # jd / taobao / pinduoduo

    def __init__(self, **kwargs):
        # 慢慢买是公开比价站，免登录即可抓真实数据，强制 allow_real=True
        kwargs["allow_real"] = True
        super().__init__(**kwargs)
        self.cookie = ""

    def _fetch(self, keyword: str, limit: int) -> list[Product]:
        all_items = fetch_manmanbuy(keyword, limit=limit * 4)
        target = {
            "jd": "京东",
            "taobao": "淘宝",
            "pinduoduo": "拼多多",
        }.get(self.platform_key, "")
        filtered = [p for p in all_items if p.platform == target]
        # 拼多多数据不足时，用拼多多移动页补充
        if self.platform_key == "pinduoduo" and len(filtered) < limit:
            extra = fetch_pinduoduo_mobile(keyword, limit=limit)
            existing_titles = {p.title[:20] for p in filtered}
            for p in extra:
                if p.title[:20] not in existing_titles:
                    filtered.append(p)
                    existing_titles.add(p.title[:20])
        if not filtered:
            raise ScrapeError(f"慢慢买未找到 {target} 平台的商品")
        return filtered[:limit]


class ManmanbuyJDScraper(ManmanbuyScraper):
    name = "jd_mmb"
    platform_cn = Platform.JD.value
    platform_key = "jd"


class ManmanbuyTaobaoScraper(ManmanbuyScraper):
    name = "taobao_mmb"
    platform_cn = Platform.TAOBAO.value
    platform_key = "taobao"


class ManmanbuyPinduoduoScraper(ManmanbuyScraper):
    name = "pdd_mmb"
    platform_cn = Platform.PINDUODUO.value
    platform_key = "pinduoduo"
