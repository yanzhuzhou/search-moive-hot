"""拼多多采集器。

真实采集思路（受限环境下会回退到演示数据）：
1. 拼多多无 PC 公开搜索页，搜索走 mobile.yangkeduo.com / api.pinduoduo.com；
2. 接口 api.pinduoduo.com/api/crawling/search 需要带 anti_content 风控参数，
   该参数由 JS 运行时生成，无法在纯 Python 中稳定构造；
3. 因此本采集器在无风控参数下会触发回退。
保留接口结构，以便后续接入 playwright/风控中间件。
"""
from __future__ import annotations

import re

from ..models import Product, Platform
from .base import BaseScraper, ScrapeError

_PDD_API = "https://mobile.yangkeduo.com/proxy/api/api/goods/goods-search"


class PinduoduoScraper(BaseScraper):
    name = "pinduoduo"
    platform_cn = Platform.PINDUODUO.value

    def __init__(self, *args, anti_content: str = "", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.anti_content = anti_content

    def _fetch(self, keyword: str, limit: int) -> list[Product]:
        if not self.anti_content:
            raise ScrapeError("拼多多需要 anti_content 风控参数，当前未提供")
        params = {
            "keyword": keyword,
            "offset": "0",
            "limit": str(limit),
            "anti_content": self.anti_content,
        }
        data = self._http_get_json(_PDD_API, params=params,
                                  headers={"Referer": "https://mobile.yangkeduo.com/"})
        items = data.get("goods_list", []) if isinstance(data, dict) else []
        if not items:
            raise ScrapeError("拼多多接口未返回商品")
        products: list[Product] = []
        for it in items[:limit]:
            try:
                price = float(it.get("min_normal_price", 0)) / 100  # 接口价格为分
            except (TypeError, ValueError):
                price = 0.0
            products.append(Product(
                platform=self.platform_cn,
                title=it.get("goods_name", "拼多多商品"),
                price=price,
                sales=it.get("sales_tip", 0) if isinstance(it.get("sales_tip"), int) else
                       _parse_pdd_sales(it.get("sales_tip", "")),
                shop=it.get("mall_name", "拼多多旗舰店"),
                shop_rating=float(it.get("mall_rating", 4.7)),
                url=f"https://mobile.yangkeduo.com/goods.html?goods_id={it.get('goods_id','')}",
                sku_id=str(it.get("goods_id", "")),
                source="real",
            ))
        return products


def _parse_pdd_sales(text: str) -> int:
    """'已拼1.2万件' -> 12000。"""
    m = re.search(r'([\d.]+)\s*万', text or "")
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'(\d+)', text or "")
    return int(m.group(1)) if m else 0
