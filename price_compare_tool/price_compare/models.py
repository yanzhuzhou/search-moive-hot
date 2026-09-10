"""统一商品数据模型。

所有平台适配器最终都把抓取到的原始字段归一化到 `Product`，
便于后续清洗、去重、对比与可视化。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Source(str, Enum):
    """支持的电商平台来源。"""

    JD = "京东"
    TAOBAO = "淘宝"
    PDD = "拼多多"


@dataclass
class Product:
    """归一化后的商品实体。

    字段含义：
        platform     : 来源平台（京东/淘宝/拼多多）
        keyword      : 本次采集使用的搜索关键词
        title        : 商品标题（已去营销前缀/后缀）
        price        : 商品价格（元），已转为 float
        sales        : 销量（已归一为整数件数）
        shop_name    : 店铺名称
        shop_score   : 店铺评分（0-5 分制，已归一）
        url          : 商品落地页链接
        sku_id       : 平台内唯一商品 ID（用于去重）
        raw          : 原始字段快照（dict，调试与溯源用）
    """

    platform: str
    keyword: str
    title: str
    price: float
    sales: int
    shop_name: str
    shop_score: float
    url: str
    sku_id: str
    raw: dict = field(default_factory=dict, repr=False)

    # —— 计算字段，由对比引擎回填 ——
    value_score: Optional[float] = None  # 性价比分（0-100）
    trend: Optional[str] = None  # 价格趋势："下降"/"持平"/"上升"/"新低"
    recommend_tag: Optional[str] = None  # 推荐标签：性价比之选/全网最低/销量冠军/品质优选/暂不推荐

    def to_dict(self) -> dict:
        d = asdict(self)
        # raw 通常体积较大，导出时折叠
        d.pop("raw", None)
        return d
