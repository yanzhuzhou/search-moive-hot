"""电商商品价格自动化采集与对比工具。

模块组成：
    models      - 商品数据模型
    scrapers    - 各平台采集器（京东/淘宝/拼多多）
    processor   - 数据清洗 / 去重 / 排序
    analyzer    - 横向对比 / 性价比推荐 / 价格趋势
    visualizer  - CLI 文本图表 / Web JSON 输出
    demo_data   - 离线演示数据生成器（真实采集失败时回退）
"""

from .models import Product, Platform

__version__ = "1.0.0"
__all__ = ["Product", "Platform"]
