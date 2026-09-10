"""淘宝适配器。

真实接口参考（移动端搜索）：
    https://h5api.m.taobao.com/h5/mtop.research.wd.search/...
返回字段：title / price / sale / item_id / nick（店铺名）/
shopcard（店铺评分）/ item_url

模拟生成器按上述字段名产出，与真实接口切换无缝衔接。
"""
from __future__ import annotations

import random
from typing import Iterable

from ..models import Product, Source
from .base import BaseAdapter


_SHOPS = ["天猫官方旗舰店", "淘宝企业店", "品牌直营店", "国货精选店",
          "源头工厂店", "海外专营店", "潮品数码专营店", "生活家居馆",
          "潮流数码旗舰店", "品牌官方旗舰店"]


class TaobaoAdapter(BaseAdapter):
    platform = Source.TAOBAO.value
    USE_MOCK = True

    def fetch_raw(self, keyword: str, limit: int) -> Iterable[dict]:
        raise NotImplementedError("请实现真实淘宝搜索接口，或保持 USE_MOCK=True 使用演示数据。")

    def normalize(self, raw: dict, keyword: str) -> Product | None:
        try:
            price = float(raw.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        return Product(
            platform=self.platform,
            keyword=keyword,
            title=title,
            price=round(price, 2),
            sales=int(raw.get("sale", 0) or 0),
            shop_name=(raw.get("nick") or "淘宝商家").strip(),
            shop_score=float(raw.get("shopcard", 4.6) or 4.6),
            url=raw.get("item_url") or f"https://item.taobao.com/item.htm?id={raw.get('item_id','')}",
            sku_id=str(raw.get("item_id") or ""),
            raw=raw,
        )

    def _make_one_mock(self, rng: random.Random, keyword: str, idx: int) -> dict:
        base = rng.uniform(19.9, 1999.0)
        price = round(base * rng.uniform(0.85, 1.05), 2)
        # 销量按"件/月"，淘宝销量普遍较大
        sale = rng.randint(50, 200000)
        shop = rng.choice(_SHOPS)
        item_id = str(rng.randint(600000000000, 699999999999))
        titles = [
            f"{keyword} 包邮 {rng.choice(['现货','新品','热销'])} {rng.choice(['官方旗舰','品牌直营'])}",
            f"【现货速发】{keyword} {rng.choice(['品质保证','七天无理由退换'])} 淘宝直营",
            f"{keyword} {rng.choice(['买一送一','第二件半价','满减'])} {rng.choice(['包邮','顺丰'])}",
            f"工厂直供 {keyword} {rng.choice(['正品保证','假一赔十'])} {rng.choice(['热销爆款','人气推荐'])}",
        ]
        return {
            "title": rng.choice(titles),
            "price": price,
            "sale": sale,
            "nick": shop,
            "shopcard": round(rng.uniform(4.4, 4.95), 2),
            "item_id": item_id,
            "item_url": f"https://item.taobao.com/item.htm?id={item_id}",
        }
