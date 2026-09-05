"""淘宝采集器。

真实采集思路（受限环境下会回退到演示数据）：
1. 淘宝搜索 https://s.taobao.com/search?q=... 需要登录态 cookie（_m_h5_tk 等），
   未登录会重定向到登录页；
2. 其 JSON 接口 https://h5api.m.taobao.com/h5/mtop.relationsearch.wirelesspc.search/1.0/
   需要签名 token，签名算法涉及 JS 混淆，无法在纯 Python 中稳定复现；
3. 因此本采集器在无登录态下会触发回退。
保留接口结构，以便在具备合法 cookie 时直接接入。
"""
from __future__ import annotations

import json
import re

from ..models import Product, Platform
from .base import BaseScraper, ScrapeError

_TAOBAO_SEARCH = "https://s.taobao.com/search"
_TAOBAO_API = "https://h5api.m.taobao.com/h5/mtop.relationsearch.wirelesspc.search/1.0/"


class TaobaoScraper(BaseScraper):
    name = "taobao"
    platform_cn = Platform.TAOBAO.value

    def __init__(self, *args, cookie: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.cookie = cookie

    def _fetch(self, keyword: str, limit: int) -> list[Product]:
        if not self.cookie:
            raise ScrapeError("淘宝需要登录态 cookie，当前未提供")
        html = self._http_get(
            _TAOBAO_SEARCH,
            params={"q": keyword, "imgfile": "", "js": "1", "stats_click": "search_radio_all"},
            headers={"Cookie": self.cookie},
        )
        # 淘宝把数据塞在 window.__pageData__ / g_page_config 里
        data = self._extract_page_data(html)
        items = data.get("mods", {}).get("itemlist", {}).get("data", {}).get("auctions", [])
        if not items:
            raise ScrapeError("淘宝页面未解析到商品（可能被反爬）")
        products: list[Product] = []
        for it in items[:limit]:
            raw_price = it.get("view_price") or it.get("priceShow") or "0"
            try:
                price = float(re.sub(r'[^\d.]', '', str(raw_price)))
            except ValueError:
                price = 0.0
            products.append(Product(
                platform=self.platform_cn,
                title=it.get("raw_title") or it.get("title", "淘宝商品"),
                price=price,
                sales=_parse_sales(it.get("view_sales", "0人付款")),
                shop=it.get("nick", "未知店铺"),
                shop_rating=float(it.get("shopcard", {}).get("rate", 4.7)),
                url=it.get("detail_url") or f"https://item.taobao.com/item.htm?id={it.get('nid','')}",
                sku_id=it.get("nid", ""),
                source="real",
            ))
        return products

    def _extract_page_data(self, html: str) -> dict:
        # 兼容 g_page_config 与 window.__pageData__
        for pat in (r'g_page_config\s*=\s*(\{.*?\})\s*</script>',
                    r'window\.__pageData__\s*=\s*(\{.*?\});'):
            m = re.search(pat, html, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        return {}


def _parse_sales(text: str) -> int:
    """把 '1.2万人付款' / '收货 543' 解析为整数。"""
    import re
    m = re.search(r'([\d.]+)\s*万', text or "")
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'(\d+)', text or "")
    return int(m.group(1)) if m else 0
