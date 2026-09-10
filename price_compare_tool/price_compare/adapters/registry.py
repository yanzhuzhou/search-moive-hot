"""适配器注册表。

新增平台只需在此注册。CLI 与 Web 通过 `get_adapter` 按名字取实例。
"""
from __future__ import annotations

from typing import Dict, List, Type

from .base import BaseAdapter
from .jd import JDAdapter
from .taobao import TaobaoAdapter
from .pdd import PDDAdapter


_REGISTRY: Dict[str, Type[BaseAdapter]] = {
    "jd": JDAdapter,
    "taobao": TaobaoAdapter,
    "pdd": PDDAdapter,
    # 中文别名，方便 CLI 传参
    "京东": JDAdapter,
    "淘宝": TaobaoAdapter,
    "拼多多": PDDAdapter,
}


def get_adapter(name: str) -> BaseAdapter:
    """按名字获取适配器实例。未注册时抛出 KeyError。"""
    key = name.strip().lower()
    if key not in _REGISTRY:
        # 尝试中文原样匹配
        if name.strip() in _REGISTRY:
            return _REGISTRY[name.strip()]()
        raise KeyError(f"未注册的适配器：{name}。可用：{list_adapters()}")
    return _REGISTRY[key]()


def list_adapters() -> List[str]:
    """返回去重后的平台标识符列表。"""
    seen = []
    for k in _REGISTRY:
        if k not in seen:
            seen.append(k)
    return seen


def all_default_adapters() -> List[BaseAdapter]:
    """返回默认启用集合（去重，按 JD/TAOBAO/PDD 顺序）。"""
    return [JDAdapter(), TaobaoAdapter(), PDDAdapter()]
