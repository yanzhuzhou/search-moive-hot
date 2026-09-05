"""京东采集器。

真实采集思路（受限环境下会回退到演示数据）：
1. 京东搜索结果页 https://search.jd.com/Search?keyword=...&enc=utf-8
   服务端返回的 HTML 中包含商品卡，价格通过后续 ajax 接口
   https://p.3.cn/prices/mgets?skuIds=J_skuId 返回；
2. 京东对未登录、无 cookie 的请求普遍返回反爬页或 302 跳登录；
3. 本采集器先尝试直接请求搜索页并解析商品卡，失败则回退。
"""
from __future__ import annotations

import re

from ..models import Product, Platform
from .base import BaseScraper, ScrapeError

_JD_SEARCH = "https://search.jd.com/Search"
# 价格接口（历史公开接口，可能已变更）
_JD_PRICE_API = "https://p.3.cn/prices/mgets"


class JDScraper(BaseScraper):
    name = "jd"
    platform_cn = Platform.JD.value

    def _fetch(self, keyword: str, limit: int) -> list[Product]:
        # 1) 抓搜索结果页
        html = self._http_get(_JD_SEARCH, params={"keyword": keyword, "enc": "utf-8"})
        if not html or "J_goodsList" not in html and "gl-item" not in html:
            # 命中反爬 / 登录墙
            raise ScrapeError("京东返回反爬/登录页，无法解析")

        # 2) 解析商品卡（正则解析 HTML，简化但可行）
        items = self._parse_items(html)
        if not items:
            raise ScrapeError("京东页面未解析到商品")

        # 3) 批量取价（可能失败，失败则用页面内显示价）
        products: list[Product] = []
        for it in items[:limit]:
            price = self._fetch_price(it["sku_id"]) or it.get("price", 0.0)
            products.append(Product(
                platform=self.platform_cn,
                title=it["title"],
                price=float(price) if price else 0.0,
                sales=it.get("sales", 0),
                shop=it.get("shop", "未知店铺"),
                shop_rating=float(it.get("shop_rating", 4.8)),
                url=it.get("url") or f"https://item.jd.com/{it['sku_id']}.html",
                sku_id=it["sku_id"],
                source="real",
            ))
        return products

    def _parse_items(self, html: str) -> list[dict]:
        items: list[dict] = []
        # 商品块：<li class="gl-item" data-sku="123456">
        blocks = re.findall(
            r'<li[^>]*class="[^"]*gl-item[^"]*"[^>]*data-sku="(\d+)"[^>]*>(.*?)</li>',
            html, re.S)
        for sku, block in blocks:
            title = ""
            m = re.search(r'<em[^>]*>(.*?)</em>', block, re.S)
            if m:
                title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            price_m = re.search(r'i-price[^>]*>(\d+\.?\d*)', block)
            shop_m = re.search(r'data-shop-name="([^"]+)"', block)
            items.append({
                "sku_id": sku,
                "title": title or f"京东商品 {sku}",
                "price": float(price_m.group(1)) if price_m else 0.0,
                "sales": 0,
                "shop": shop_m.group(1) if shop_m else "京东自营",
                "shop_rating": 4.8,
                "url": f"https://item.jd.com/{sku}.html",
            })
        return items

    def _fetch_price(self, sku_id: str) -> float | None:
        try:
            data = self._http_get_json(_JD_PRICE_API, params={"skuIds": f"J_{sku_id}"})
            if isinstance(data, list) and data:
                return float(data[0].get("p", 0) or 0)
        except ScrapeError:
            return None
        return None
