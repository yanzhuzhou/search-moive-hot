"""采集-对比引擎。

把"适配器采集 → 清洗去重 → 对比标注 → 摘要"组装成一次调用，
CLI 与 Web 共用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List

from .adapters.base import BaseAdapter
from .adapters.registry import all_default_adapters, get_adapter
from .cleaner import clean
from .comparator import annotate, summary
from .models import Product
from . import visualizer


@dataclass
class CompareResult:
    keyword: str
    products: List[Product]
    summary: Dict[str, Any]
    chart_html: str
    raw_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "raw_count": self.raw_count,
            "count": len(self.products),
            "summary": self.summary,
            "products": [p.to_dict() for p in self.products],
            "chart_html": self.chart_html,
        }


class CompareEngine:
    """采集对比引擎：默认启用三大平台，可自定义。"""

    def __init__(self, adapters: List[BaseAdapter] | None = None):
        self.adapters = adapters or all_default_adapters()

    def run(self, keyword: str, per_platform: int = 10) -> CompareResult:
        """对关键词执行完整采集-对比流程。"""
        if not keyword or not keyword.strip():
            raise ValueError("关键词不能为空")

        all_raw: List[Product] = []
        for adapter in self.adapters:
            try:
                all_raw.extend(adapter.search(keyword, limit=per_platform))
            except Exception as e:  # 单平台失败不阻塞其它平台
                print(f"[warn] {adapter.platform} 采集失败：{e}")

        raw_count = len(all_raw)
        cleaned = clean(all_raw)
        annotate(cleaned)
        s = summary(cleaned)
        chart_html = visualizer.to_chart_html(cleaned, keyword) if cleaned else ""

        return CompareResult(
            keyword=keyword,
            products=cleaned,
            summary=s,
            chart_html=chart_html,
            raw_count=raw_count,
        )

    @staticmethod
    def with_platforms(names: List[str]) -> "CompareEngine":
        """按平台名列表构造引擎。"""
        adapters = [get_adapter(n) for n in names]
        return CompareEngine(adapters=adapters)
