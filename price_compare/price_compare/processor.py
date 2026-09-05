"""数据清洗 / 去重 / 排序。"""
from __future__ import annotations

import re
from typing import Iterable

from .models import Product


def clean(products: list[Product]) -> list[Product]:
    """清洗：去空白、规范化价格/销量、丢弃无效记录。"""
    out: list[Product] = []
    for p in products:
        p.title = _clean_title(p.title)
        p.price = _clean_price(p.price)
        p.sales = _clean_sales(p.sales)
        p.shop = (p.shop or "").strip() or "未知店铺"
        p.shop_rating = max(1.0, min(5.0, float(p.shop_rating or 0.0)))
        # 价格异常或缺失则丢弃
        if p.price <= 0:
            continue
        out.append(p)
    return out


def dedup(products: list[Product]) -> list[Product]:
    """去重：同平台同 sku_id 去重；其次按指纹去重。"""
    seen_sku: set[tuple[str, str]] = set()
    seen_fp: set[str] = set()
    out: list[Product] = []
    for p in products:
        if p.sku_id:
            k = (p.platform, p.sku_id)
            if k in seen_sku:
                continue
            seen_sku.add(k)
        fp = p.fingerprint()
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        out.append(p)
    return out


def sort_by_price(products: Iterable[Product], asc: bool = True) -> list[Product]:
    """按价格排序，相同价时销量高者优先。"""
    return sorted(products, key=lambda p: (p.price, -p.sales), reverse=not asc)


def process(products: list[Product]) -> list[Product]:
    """清洗 -> 去重 -> 按价格升序排序，返回最终商品列表。"""
    return sort_by_price(dedup(clean(list(products))))


# ---- 字段清洗细节 ----------------------------------------------------
_TITLE_NOISE = re.compile(r'【|】|\s+')


def _clean_title(title: str) -> str:
    if not title:
        return "未命名商品"
    # 压缩空白与冗余符号
    t = title.replace("<em>", "").replace("</em>", "")
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _clean_price(price) -> float:
    try:
        if isinstance(price, str):
            # "99.00-199.00" 取下界
            m = re.search(r'([\d.]+)', price)
            if not m:
                return 0.0
            return float(m.group(1))
        return float(price)
    except (TypeError, ValueError):
        return 0.0


def _clean_sales(sales) -> int:
    """统一解析 '1.2万' / '已拼1.2万件' / 123 / '123'。"""
    if isinstance(sales, (int, float)):
        try:
            return int(sales)
        except (TypeError, ValueError):
            return 0
    if not sales:
        return 0
    s = str(sales)
    m = re.search(r'([\d.]+)\s*万', s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r'(\d+)', s)
    return int(m.group(1)) if m else 0
