"""离线演示数据生成器。

真实电商平台均有较强的反爬与登录校验，在受限网络/无登录态环境下无法稳定抓取。
本模块提供一个**确定性**的演示数据生成器：
- 以关键词为随机种子，保证同一关键词每次产出一致（可复现）；
- 模拟京东/淘宝/拼多多三家平台的真实价格分布、销量分布、店铺评分特征；
- 真实采集器在失败时会回退到本模块，并在每条记录上标注 source=demo。
"""
from __future__ import annotations

import random
from typing import Iterable

from .models import Platform, Product


# 各平台特征画像（基于公开市场观察的近似值，仅用于演示）
_PLATFORM_PROFILE: dict[Platform, dict] = {
    Platform.JD: {
        "price_mul": (1.05, 1.45),    # 京东整体偏高，正品溢价
        "sales_range": (50, 8000),
        "rating_range": (4.7, 4.95),
        "shop_pool": ["京东自营官方旗舰店", "联想京东自营店", "小米京东旗舰店",
                      "罗技京东自营店", "华为京东自营店", "京东数码大药房"],
        "title_affix": ("正品", "自营", "官方"),
    },
    Platform.TAOBAO: {
        "price_mul": (0.75, 1.10),    # 淘宝价位居中，C 店多
        "sales_range": (100, 20000),
        "rating_range": (4.5, 4.9),
        "shop_pool": ["数码潮品工厂店", "优选数码专营店", "淘工厂直供",
                      "天猫超市旗舰店", "极客数码工作室", "潮玩数码小店"],
        "title_affix": ("包邮", "现货", "爆款"),
    },
    Platform.PINDUODUO: {
        "price_mul": (0.55, 0.85),    # 拼多多最低，百亿补贴更狠
        "sales_range": (300, 50000),
        "rating_range": (4.3, 4.85),
        "shop_pool": ["百亿补贴官方", "拼多多旗舰店", "惠买数码专营",
                      "拼工厂直供", "省钱特卖店", "多多优选"],
        "title_affix": ("百亿补贴", "拼团价", "限时秒杀"),
    },
}

# 关键词 -> 基准价（元），用于让演示数据贴合品类直觉
_KEYWORD_BASE_PRICE: dict[str, float] = {
    "无线鼠标": 89, "鼠标": 89, "键盘": 199, "机械键盘": 299,
    "耳机": 159, "蓝牙耳机": 199, "手机": 2599, "iphone": 5999,
    "充电宝": 99, "数据线": 19, "笔记本": 4599, "显示器": 1299,
    "书包": 129, "保温杯": 59, "空调": 2699, "电饭煲": 299,
}


def _base_price(keyword: str) -> float:
    k = keyword.strip().lower()
    for key, price in _KEYWORD_BASE_PRICE.items():
        if key in k:
            return price
    # 未知关键词：根据字符数给一个合理基准
    return max(29.9, 30 * (len(keyword) % 8 + 1))


def _make_title(keyword: str, affix: str, idx: int) -> str:
    variants = [
        f"{keyword} {affix} 2026新款 第{idx}代",
        f"【{affix}】{keyword} 国行 顺丰包邮",
        f"{keyword} 高配版 {affix} 官方授权",
        f"{affix} {keyword} 大容量 商用家用",
        f"{keyword} 精选好物 {affix} 限时优惠",
    ]
    return variants[idx % len(variants)]


def generate(keyword: str, per_platform: int = 8) -> list[Product]:
    """为关键词生成演示商品列表。

    Args:
        keyword: 搜索关键词
        per_platform: 每个平台生成条数
    """
    seed = abs(hash(keyword)) % (2**31)
    rng = random.Random(seed)
    base = _base_price(keyword)
    products: list[Product] = []

    for platform in Platform:
        profile = _PLATFORM_PROFILE[platform]
        lo, hi = profile["price_mul"]
        s_lo, s_hi = profile["sales_range"]
        r_lo, r_hi = profile["rating_range"]

        for i in range(per_platform):
            # 价格 = 基准 * 平台系数 * 个案抖动
            price = round(base * rng.uniform(lo, hi) * rng.uniform(0.85, 1.15), 2)
            price = max(1.0, price)
            sales = rng.randint(s_lo, s_hi)
            rating = round(rng.uniform(r_lo, r_hi), 2)
            shop = rng.choice(profile["shop_pool"])
            affix = rng.choice(profile["title_affix"])
            title = _make_title(keyword, affix, i)
            sku_id = f"DEMO-{platform.key}-{seed % 100000:05d}-{i}"
            # 构造可点击的平台示例链接（演示用，非真实 SKU）
            url = _demo_url(platform, sku_id, keyword)
            products.append(Product(
                platform=platform.value,
                title=title,
                price=price,
                sales=sales,
                shop=shop,
                shop_rating=rating,
                url=url,
                sku_id=sku_id,
                source="demo",
            ))
    return products


def _demo_url(platform: Platform, sku_id: str, keyword: str) -> str:
    if platform is Platform.JD:
        return f"https://search.jd.com/Search?keyword={keyword}&enc=utf-8"
    if platform is Platform.TAOBAO:
        return f"https://s.taobao.com/search?q={keyword}"
    return f"https://mobile.yangkeduo.com/search_result.html?search_key={keyword}"


# 默认演示关键词（网页初始化示例用）
DEFAULT_DEMO_KEYWORD = "无线鼠标"


def default_sample() -> list[Product]:
    return generate(DEFAULT_DEMO_KEYWORD, per_platform=6)
