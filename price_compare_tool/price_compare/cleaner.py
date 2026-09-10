"""数据清洗、去重、排序模块。

输入：来自多个平台适配器的 `Product` 列表（可能含噪声、重复、缺失）。
输出：清洗去重后的 `Product` 列表，按价格从低到高排序。

清洗规则：
1. 丢弃价格<=0、标题为空、sku_id 为空的条目；
2. 标题去营销前缀（【...】、[...]）与多余空白；
3. 店铺评分越界裁剪到 [0,5]；
4. 销量归一为整数；
5. 跨平台去重：同一关键词下 title 高度相似 + 价格差<2 元 视为同款；
6. 价格升序排序（用户明确要求"从低到高"）。
"""
from __future__ import annotations

import re
from typing import List

from .models import Product


_PREFIX_RE = re.compile(r"^\s*[【\[（(]\s*[^】\]）)]{0,12}[】\]）)]\s*")
_MULTI_SPACE_RE = re.compile(r"\s+")


def _clean_title(title: str) -> str:
    """去除常见营销前缀【】/[]/()与多余空白。保留主体语义。"""
    t = _PREFIX_RE.sub("", title)
    t = _MULTI_SPACE_RE.sub(" ", t).strip()
    return t


def _normalize_price(p: Product) -> None:
    if p.price < 0:
        p.price = 0.0
    p.price = round(p.price, 2)


def _normalize_score(p: Product) -> None:
    if p.shop_score < 0:
        p.shop_score = 0.0
    elif p.shop_score > 5:
        p.shop_score = 5.0
    p.shop_score = round(p.shop_score, 2)


def _normalize_sales(p: Product) -> None:
    if p.sales < 0:
        p.sales = 0


def _title_key(title: str) -> str:
    """生成去重用的标题相似键：去掉所有非汉字字母数字字符后小写。

    这样"【现货】蓝牙耳机 5.0" 与 "蓝牙耳机5.0 现货" 会被视为同款候选。
    """
    return re.sub(r"[^\w\u4e00-\u9fa5]", "", title).lower()


def _is_duplicate(a: Product, b: Product) -> bool:
    """判断两个商品是否为同款。

    判定顺序：
    1. 平台内严格按 sku_id 去重；
    2. 跨平台：标题相似键长度>=6 且（完全一致 或 互为子串）+ 价格差<阈值。
       互为子串可覆盖"蓝牙耳机5.0"与"蓝牙耳机5.0现货包邮"这类营销后缀差异。
    """
    # 平台内严格按 sku_id 去重
    if a.platform == b.platform and a.sku_id and b.sku_id:
        return a.sku_id == b.sku_id
    ka, kb = _title_key(a.title), _title_key(b.title)
    if len(ka) < 6 or len(kb) < 6:
        return False
    # 价格阈值：低价商品更严格，高价商品放宽（相对 5% 或绝对 2 元取大）
    threshold = max(2.0, min(a.price, b.price) * 0.05)
    if abs(a.price - b.price) >= threshold:
        return False
    if ka == kb:
        return True
    # 互为子串：处理营销后缀差异（现货/包邮/正品保证…）
    # 较短标题键长度>=6 即可作为匹配基底
    short, long_ = (ka, kb) if len(ka) <= len(kb) else (kb, ka)
    if len(short) >= 6 and short in long_:
        return True
    return False


def clean(products: List[Product]) -> List[Product]:
    """完整清洗流程：归一 → 去前缀 → 去重 → 排序。"""
    cleaned: List[Product] = []
    for p in products:
        if p.price <= 0 or not p.title.strip() or not p.sku_id:
            continue
        p.title = _clean_title(p.title)
        if not p.title:
            continue
        _normalize_price(p)
        _normalize_score(p)
        _normalize_sales(p)
        cleaned.append(p)

    # 去重：保留同款中价格更低者
    deduped: List[Product] = []
    for p in cleaned:
        dup_idx = None
        for i, kept in enumerate(deduped):
            if _is_duplicate(p, kept):
                dup_idx = i
                break
        if dup_idx is None:
            deduped.append(p)
        else:
            kept = deduped[dup_idx]
            if p.price < kept.price:
                deduped[dup_idx] = p

    # 价格升序
    deduped.sort(key=lambda x: x.price)
    return deduped
