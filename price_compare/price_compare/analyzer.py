"""横向对比 / 性价比推荐 / 价格趋势。"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from .models import Product


@dataclass
class PlatformStats:
    platform: str
    count: int
    min_price: float
    max_price: float
    avg_price: float
    median_price: float
    min_price_product: Product | None
    best_seller: Product | None    # 销量最高

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "count": self.count,
            "min_price": self.min_price,
            "max_price": self.max_price,
            "avg_price": round(self.avg_price, 2),
            "median_price": round(self.median_price, 2),
            "min_price_product": self.min_price_product.to_dict() if self.min_price_product else None,
            "best_seller": self.best_seller.to_dict() if self.best_seller else None,
        }


def compare_by_platform(products: list[Product]) -> list[PlatformStats]:
    """按平台聚合统计。"""
    groups: dict[str, list[Product]] = {}
    for p in products:
        groups.setdefault(p.platform, []).append(p)
    stats: list[PlatformStats] = []
    for plat, items in groups.items():
        prices = [p.price for p in items]
        if not prices:
            continue
        min_p = min(items, key=lambda x: x.price)
        best = max(items, key=lambda x: x.sales)
        stats.append(PlatformStats(
            platform=plat,
            count=len(items),
            min_price=min(prices),
            max_price=max(prices),
            avg_price=statistics.mean(prices),
            median_price=statistics.median(prices),
            min_price_product=min_p,
            best_seller=best,
        ))
    return stats


def value_for_money(products: list[Product], top_n: int = 3) -> list[dict[str, Any]]:
    """性价比推荐：score = 销量 / 价格 * 店铺评分权重。

    直觉：在同等价格下，销量越高说明越被市场认可；店铺评分高更可信。
    采用 (sales / price) * rating 归一化排序，标注 Top-N。
    """
    if not products:
        return []
    scored: list[tuple[float, Product]] = []
    for p in products:
        if p.price <= 0:
            continue
        # 用对数压缩销量，避免爆款完全压倒
        import math
        score = (math.log10(p.sales + 10) / p.price) * (p.shop_rating / 5.0)
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for rank, (score, p) in enumerate(scored[:top_n], 1):
        d = p.to_dict()
        d["rank"] = rank
        d["value_score"] = round(score, 4)
        d["badge"] = "性价比优选" if rank == 1 else ("高性价比" if rank <= 3 else "")
        out.append(d)
    return out


def price_distribution(products: list[Product]) -> list[dict[str, Any]]:
    """价格趋势：把价格分成 6 档，统计各档商品数与平台分布。"""
    if not products:
        return []
    prices = [p.price for p in products]
    lo, hi = min(prices), max(prices)
    if hi <= lo:
        hi = lo + 1
    bins = 6
    edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    buckets = [{"label": f"¥{edges[i]:.0f}-{edges[i+1]:.0f}",
                "range": [round(edges[i], 2), round(edges[i+1], 2)],
                "count": 0, "platforms": {}} for i in range(bins)]
    for p in products:
        idx = min(bins - 1, int((p.price - lo) / (hi - lo) * bins))
        buckets[idx]["count"] += 1
        buckets[idx]["platforms"].setdefault(p.platform, 0)
        buckets[idx]["platforms"][p.platform] += 1
    return buckets


def platform_trend(products: list[Product]) -> list[dict[str, Any]]:
    """各平台价格箱线趋势：返回每个平台的 [min, Q1, median, Q3, max]。"""
    groups: dict[str, list[float]] = {}
    for p in products:
        groups.setdefault(p.platform, []).append(p.price)
    out: list[dict[str, Any]] = []
    for plat, prices in groups.items():
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        if n == 0:
            continue

        def quantile(q: float) -> float:
            k = (n - 1) * q
            f = int(k)
            c = k - f
            if f + 1 < n:
                return prices_sorted[f] + c * (prices_sorted[f + 1] - prices_sorted[f])
            return prices_sorted[f]
        out.append({
            "platform": plat,
            "min": round(prices_sorted[0], 2),
            "q1": round(quantile(0.25), 2),
            "median": round(quantile(0.5), 2),
            "q3": round(quantile(0.75), 2),
            "max": round(prices_sorted[-1], 2),
            "count": n,
        })
    return out


def analyze(products: list[Product]) -> dict[str, Any]:
    """综合分析：返回对比/趋势/推荐的整体结果。"""
    return {
        "platform_stats": [s.to_dict() for s in compare_by_platform(products)],
        "price_distribution": price_distribution(products),
        "platform_trend": platform_trend(products),
        "value_picks": value_for_money(products, top_n=3),
        "total": len(products),
    }
