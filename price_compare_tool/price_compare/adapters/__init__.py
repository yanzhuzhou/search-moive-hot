"""平台适配器子包。

每个适配器负责把对应电商平台的原始搜索接口响应，归一化为
`Product` 列表。新增平台只需继承 `BaseAdapter` 并在 `registry.py`
注册即可，无需改动核心清洗/对比/可视化逻辑。
"""
from .base import BaseAdapter
from .jd import JDAdapter
from .taobao import TaobaoAdapter
from .pdd import PDDAdapter
from .registry import get_adapter, list_adapters

__all__ = [
    "BaseAdapter",
    "JDAdapter",
    "TaobaoAdapter",
    "PDDAdapter",
    "get_adapter",
    "list_adapters",
]
