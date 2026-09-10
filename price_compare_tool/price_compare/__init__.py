"""电商商品价格自动化采集与对比工具包。

提供从京东 / 淘宝 / 拼多多采集商品信息、清洗去重、横向对比、
性价比推荐与可视化的完整能力。CLI 与 Web 演示页共用本包。
"""
from .models import Product, Source
from .engine import CompareEngine

__all__ = ["Product", "Source", "CompareEngine"]
__version__ = "1.0.0"
