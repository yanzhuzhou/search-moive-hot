"""商品数据模型与平台枚举。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Platform(str, Enum):
    JD = "京东"
    TAOBAO = "淘宝"
    PINDUODUO = "拼多多"

    @property
    def key(self) -> str:
        return {"京东": "jd", "淘宝": "taobao", "拼多多": "pinduoduo"}[self.value]


@dataclass
class Product:
    """单条商品记录。"""
    platform: str            # 平台中文名
    title: str               # 商品标题
    price: float             # 人民币价格（元）
    sales: int               # 月销量
    shop: str                # 店铺名称
    shop_rating: float       # 店铺评分（1-5）
    url: str                 # 商品页 URL
    sku_id: str = ""         # 平台内部 SKU 标识
    source: str = "real"     # real=真实抓取 / demo=演示数据
    extra: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self) -> str:
        """用于去重的指纹：平台 + 标题前 40 字 + 价格区间桶。"""
        raw = f"{self.platform}|{self.title[:40]}|{int(self.price)}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Product":
        return Product(**d)
