"""横向对比与性价比推荐模块。

输入：清洗去重后的 `Product` 列表。
输出：每个商品的 value_score（0-100）、trend、recommend_tag，以及
跨平台的横向统计指标。

性价比评分公式（可解释的加权，便于在 Web 上展示）：
    value_score = 50 * (1 - price_norm)
                + 25 * sales_norm
                + 15 * score_norm
                + 10 * platform_bonus
其中各 *_norm 为该维度在当前关键词集合内的 min-max 归一。
平台补贴：京东+5（自营正品保障）、淘宝+3、拼多多+2（默认）。

推荐标签规则（互斥，按优先级）：
    全网最低  : 价格为当前集合最低
    性价比之选: value_score 全集前三且评分>=4.5
    销量冠军  : 销量全集第一
    品质优选  : 店铺评分最高且>=4.9
    暂不推荐  : value_score<40 或 评分<4.0
    其余      : None
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any

from .models import Product


_PLATFORM_BONUS = {"京东": 0.05, "淘宝": 0.03, "拼多多": 0.02}


def _minmax(values: List[float]) -> List[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def annotate(products: List[Product]) -> None:
    """对每个商品原地填充 value_score / trend / recommend_tag。"""
    if not products:
        return

    prices = [p.price for p in products]
    sales = [float(p.sales) for p in products]
    scores = [p.shop_score for p in products]

    price_norm = _minmax(prices)        # 价格越低越好 → 1 - norm
    sales_norm = _minmax(sales)          # 销量越高越好
    score_norm = _minmax(scores)         # 评分越高越好

    min_price = min(prices)
    max_sales = max(sales)
    max_score = max(scores)

    computed: List[tuple] = []  # (value_score, recommend_tag)
    for i, p in enumerate(products):
        platform_bonus = _PLATFORM_BONUS.get(p.platform, 0.0)
        value_score = (
            50.0 * (1.0 - price_norm[i])
            + 25.0 * sales_norm[i]
            + 15.0 * score_norm[i]
            + 10.0 * platform_bonus
        )
        value_score = round(max(0.0, min(100.0, value_score)), 1)
        p.value_score = value_score

        # 趋势：相对最低价的位置。这里用"价格分位"近似：
        # 处于最低 10% 标"新低"（贴近最低价），其余按价格分位标"上升/持平"
        # 真实场景应由历史价格序列计算，本演示用相对位置近似并标注。
        if p.price <= min_price * 1.05:
            p.trend = "新低"
        elif price_norm[i] <= 0.33:
            p.trend = "下降"
        elif price_norm[i] >= 0.66:
            p.trend = "上升"
        else:
            p.trend = "持平"

        # 推荐标签（互斥，按优先级判定）
        tag: Optional[str] = None
        if p.price <= min_price * 1.02:
            tag = "全网最低"
        elif value_score < 40 or p.shop_score < 4.0:
            tag = "暂不推荐"
        elif p.sales >= max_sales * 0.95:
            tag = "销量冠军"
        elif p.shop_score >= max_score * 0.99 and p.shop_score >= 4.9:
            tag = "品质优选"
        elif value_score >= 70 and p.shop_score >= 4.5:
            tag = "性价比之选"
        p.recommend_tag = tag


def summary(products: List[Product]) -> Dict[str, Any]:
    """生成跨平台横向对比摘要，供可视化与报告使用。"""
    if not products:
        return {"count": 0}

    by_platform: Dict[str, List[Product]] = {}
    for p in products:
        by_platform.setdefault(p.platform, []).append(p)

    platform_stats = []
    for plat, items in by_platform.items():
        prices = [x.price for x in items]
        platform_stats.append({
            "platform": plat,
            "count": len(items),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
            "avg_price": round(sum(prices) / len(prices), 2),
            "avg_sales": int(sum(x.sales for x in items) / len(items)),
            "avg_score": round(sum(x.shop_score for x in items) / len(items), 2),
        })

    price_sorted = sorted(products, key=lambda x: x.price)
    value_sorted = sorted(products, key=lambda x: -(x.value_score or 0))

    return {
        "count": len(products),
        "platform_count": len(by_platform),
        "global_min": round(price_sorted[0].price, 2),
        "global_max": round(price_sorted[-1].price, 2),
        "global_avg": round(sum(p.price for p in products) / len(products), 2),
        "platform_stats": platform_stats,
        "cheapest": price_sorted[0].to_dict() if price_sorted else None,
        "best_value": value_sorted[0].to_dict() if value_sorted else None,
        "topseller": max(products, key=lambda x: x.sales).to_dict(),
    }
