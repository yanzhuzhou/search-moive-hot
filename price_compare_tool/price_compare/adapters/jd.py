"""京东适配器。

真实接口参考（移动端搜索）：
    https://api.m.jd.com/client.search?...&keyword=<kw>
返回字段：warename / jdPrice / commentCount / gooodRatePercent /
shopName / skuId / itemLink

模拟生成器按上述字段名产出，便于把 `fetch_raw` 切换为真实请求时
直接复用 `normalize`。
"""
from __future__ import annotations

import random
from typing import Iterable, List

from ..models import Product, Source
from .base import BaseAdapter


_BRANDS = ["京东自营", "小米官方旗舰店", "华为京东自营官方旗舰店",
           "苹果京东自营官方旗舰店", "OPPO官方旗舰店", "vivo官方旗舰店",
           "海尔京东自营旗舰店", "美的京东自营旗舰店", "索尼京东自营官方旗舰店",
           "戴尔京东自营官方旗舰店"]


class JDAdapter(BaseAdapter):
    platform = Source.JD.value
    USE_MOCK = True

    def fetch_raw(self, keyword: str, limit: int) -> Iterable[dict]:
        # 生产实现：requests.get('https://api.m.jd.com/...', params={...})
        # 需要 Cookie / 签名 / 反爬策略。此处仅留接口契约。
        raise NotImplementedError("请实现真实京东搜索接口，或保持 USE_MOCK=True 使用演示数据。")

    def normalize(self, raw: dict, keyword: str) -> Product | None:
        try:
            price = float(raw.get("jdPrice") or raw.get("price") or 0)
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        title = (raw.get("warename") or raw.get("title") or "").strip()
        if not title:
            return None
        return Product(
            platform=self.platform,
            keyword=keyword,
            title=title,
            price=round(price, 2),
            sales=int(raw.get("commentCount", 0) or 0),
            shop_name=(raw.get("shopName") or "京东自营").strip(),
            shop_score=float(raw.get("shopScore", 4.8) or 4.8),
            url=raw.get("itemLink") or f"https://item.jd.com/{raw.get('skuId','')}.html",
            sku_id=str(raw.get("skuId") or raw.get("sku") or ""),
            raw=raw,
        )

    def _make_one_mock(self, rng: random.Random, keyword: str, idx: int) -> dict:
        base = rng.uniform(29.9, 2999.0)
        # 京东普遍偏正价，店铺评分较高
        price = round(base, 2)
        sales = rng.randint(200, 80000)
        shop = rng.choice(_BRANDS)
        sku = f"1000{rng.randint(10000, 99999)}"
        titles = [
            f"【京东自营】{keyword} 旗舰款 官方正品 全国联保",
            f"{keyword} 2025新款 {rng.choice(['8GB+256GB','16GB+512GB'])} 京东自营",
            f"京东自营 {keyword} {rng.choice(['黑色','白色','蓝色'])} {rng.choice(['快充','长续航','高清'])}",
            f"{keyword} 官方旗舰店 原厂保修 {rng.choice(['套餐一','套餐二','套装'])}",
        ]
        return {
            "warename": rng.choice(titles),
            "jdPrice": price,
            "commentCount": sales,
            "shopName": shop,
            "shopScore": round(rng.uniform(4.7, 4.98), 2),
            "skuId": sku,
            "itemLink": f"https://item.jd.com/{sku}.html",
        }
