"""拼多多适配器。

真实接口参考（移动端搜索）：
    https://mobile.yangkeduo.com/proxy/api/search/...
返回字段：goods_name / goods_price / cnt（销量）/
mall_name / mall_score / goods_id / link_url

模拟生成器按上述字段名产出。
"""
from __future__ import annotations

import random
from typing import Iterable

from ..models import Product, Source
from .base import BaseAdapter


_MALLS = ["拼多多官方旗舰店", "百亿补贴官方", "源头工厂直供", "品牌特卖店",
          "九块九特卖", "万人团官方", "正品直营店", "工厂直销",
          "拼购官方", "品牌厂商店"]


class PDDAdapter(BaseAdapter):
    platform = Source.PDD.value
    USE_MOCK = True

    def fetch_raw(self, keyword: str, limit: int) -> Iterable[dict]:
        raise NotImplementedError("请实现真实拼多多搜索接口，或保持 USE_MOCK=True 使用演示数据。")

    def normalize(self, raw: dict, keyword: str) -> Product | None:
        try:
            price = float(raw.get("goods_price") or 0)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        title = (raw.get("goods_name") or "").strip()
        if not title:
            return None
        return Product(
            platform=self.platform,
            keyword=keyword,
            title=title,
            price=round(price, 2),
            sales=int(raw.get("cnt", 0) or 0),
            shop_name=(raw.get("mall_name") or "拼多多商家").strip(),
            shop_score=float(raw.get("mall_score", 4.5) or 4.5),
            url=raw.get("link_url") or f"https://mobile.yangkeduo.com/goods.html?goods_id={raw.get('goods_id','')}",
            sku_id=str(raw.get("goods_id") or ""),
            raw=raw,
        )

    def _make_one_mock(self, rng: random.Random, keyword: str, idx: int) -> dict:
        # 拼多多价格普遍最低，且更集中
        base = rng.uniform(9.9, 999.0)
        price = round(base * rng.uniform(0.7, 0.95), 2)
        cnt = rng.randint(1000, 500000)  # 拼多多销量普遍更大（拼单计数）
        mall = rng.choice(_MALLS)
        goods_id = str(rng.randint(1000000000, 9999999999))
        titles = [
            f"【百亿补贴】{keyword} {rng.choice(['正品包邮','官方旗舰'])} {rng.choice(['仅限今日','限时秒杀'])}",
            f"{keyword} {rng.choice(['万人团','拼单立减','工厂直供'])} {rng.choice(['包邮','七天退换'])}",
            f"【限时秒杀】{keyword} {rng.choice(['爆款','热销'])} {rng.choice(['假一赔十','正品保证'])}",
            f"{keyword} {rng.choice(['9.9特卖','超级爆款','源头好货'])} {rng.choice(['快速发货','现货'])}",
        ]
        return {
            "goods_name": rng.choice(titles),
            "goods_price": price,
            "cnt": cnt,
            "mall_name": mall,
            "mall_score": round(rng.uniform(4.2, 4.9), 2),
            "goods_id": goods_id,
            "link_url": f"https://mobile.yangkeduo.com/goods.html?goods_id={goods_id}",
        }
