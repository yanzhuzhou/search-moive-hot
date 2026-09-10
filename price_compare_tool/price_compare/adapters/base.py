"""适配器基类与公共工具。

真实生产环境里，每个适配器应实现 `fetch_raw(keyword, limit)`，
通过对应平台的官方/移动端搜索接口拉取数据。受反爬、登录态、
签名等因素影响，真实接口需配合 Cookie/SDK 签名/代理池使用。

为了让本工具"开箱即跑"，子类默认实现一个**确定性模拟数据生成器**：
基于关键词与一个固定随机种子，生成结构上与真实平台字段完全一致的
`Product`。把 `BaseAdapter.USE_MOCK=False` 并实现 `fetch_raw` 即可切换
到真实采集——核心清洗/对比/可视化代码无需改动。

这一点在 README 与代码注释中均有标注，避免被误当作真实在线数据。
"""
from __future__ import annotations

import abc
import hashlib
import random
from typing import Iterable, List

from ..models import Product


def _seed_from(keyword: str, salt: str = "") -> int:
    """由关键词派生稳定的随机种子，保证同一关键词多次运行结果一致。"""
    digest = hashlib.md5((salt + keyword).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class BaseAdapter(abc.ABC):
    """所有平台适配器的抽象基类。"""

    #: 平台名称（中文展示），子类覆盖
    platform: str = "未知平台"
    #: 是否使用模拟数据生成器。生产环境改为 False 并实现 fetch_raw。
    USE_MOCK: bool = True

    def search(self, keyword: str, limit: int = 20) -> List[Product]:
        """对外暴露的统一采集入口。

        1. 拉取原始数据（真实接口或模拟生成器）；
        2. 调用 `normalize` 把平台原生字段映射为 `Product`；
        3. 截断到 limit 条并打上平台标签。
        """
        if self.USE_MOCK:
            raw_items = self._mock_search(keyword, limit)
        else:
            raw_items = self.fetch_raw(keyword, limit)

        products: List[Product] = []
        for raw in raw_items[:limit]:
            p = self.normalize(raw, keyword)
            if p is not None:
                products.append(p)
        return products

    # —— 子类必须实现 ——
    @abc.abstractmethod
    def fetch_raw(self, keyword: str, limit: int) -> Iterable[dict]:
        """从真实平台接口拉取原始字段。USE_MOCK=False 时被调用。"""

    @abc.abstractmethod
    def normalize(self, raw: dict, keyword: str) -> Product | None:
        """把平台原生 dict 映射为 `Product`。返回 None 表示丢弃。"""

    # —— 模拟数据生成器（默认实现，子类可覆盖以更贴近真实分布）——
    def _mock_search(self, keyword: str, limit: int) -> List[dict]:
        seed = _seed_from(keyword, salt=self.platform)
        rng = random.Random(seed)
        items: List[dict] = []
        for i in range(limit):
            items.append(self._make_one_mock(rng, keyword, i))
        return items

    def _make_one_mock(self, rng: random.Random, keyword: str, idx: int) -> dict:
        """子类覆盖此方法以生成平台风格的原生字段。"""
        raise NotImplementedError
