"""核心逻辑单元测试：数据模型、清洗去重、对比标注、引擎编排。

运行：python -m pytest tests/ -v
  或：python tests/test_tool.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from price_compare.models import Product, Source
from price_compare.cleaner import clean
from price_compare.comparator import annotate, summary
from price_compare.engine import CompareEngine
from price_compare.adapters.jd import JDAdapter
from price_compare.adapters.taobao import TaobaoAdapter
from price_compare.adapters.pdd import PDDAdapter


def test_normalize_jd():
    ad = JDAdapter()
    raw = {"warename": "【京东自营】测试商品", "jdPrice": "99.9",
           "commentCount": "1000", "shopName": "京东自营", "shopScore": 4.9,
           "skuId": "10001", "itemLink": "http://jd/1"}
    p = ad.normalize(raw, "kw")
    assert p.platform == Source.JD.value
    assert p.price == 99.9
    assert p.sales == 1000
    assert p.shop_score == 4.9
    assert p.sku_id == "10001"


def test_normalize_drops_invalid():
    ad = TaobaoAdapter()
    assert ad.normalize({"title": "", "price": 10}, "kw") is None
    assert ad.normalize({"title": "x", "price": 0}, "kw") is None
    assert ad.normalize({"title": "x", "price": "not-num"}, "kw") is None


def test_clean_filters_and_sorts():
    ps = [
        Product("京东", "kw", "商品A", 100.0, 10, "店", 4.5, "u1", "s1"),
        Product("淘宝", "kw", "商品B", 50.0, 20, "店", 4.7, "u2", "s2"),
        Product("拼多多", "kw", "商品C", 0, 5, "店", 4.5, "u3", "s3"),  # 价格<=0 丢弃
        Product("京东", "kw", "", 30.0, 5, "店", 4.5, "u4", "s4"),       # 空标题 丢弃
    ]
    out = clean(ps)
    assert len(out) == 2
    assert out[0].price == 50.0  # 升序


def test_dedup_cross_platform_same_item():
    ps = [
        Product("京东", "kw", "【现货】蓝牙耳机 5.0", 99.0, 5000, "京东", 4.9, "u1", "jd1"),
        Product("淘宝", "kw", "蓝牙耳机5.0 现货", 98.5, 8000, "天猫", 4.7, "u2", "tb1"),
        Product("拼多多", "kw", "不同款", 50.0, 20000, "拼多多", 4.5, "u3", "pdd1"),
    ]
    out = clean(ps)
    assert len(out) == 2
    # 同款保留价格更低者(淘宝 98.5)，京东 99 被去重
    prices = [p.price for p in out]
    assert 99.0 not in prices
    assert 98.5 in prices


def test_dedup_within_platform_by_sku():
    ps = [
        Product("京东", "kw", "商品A", 99.0, 10, "店", 4.5, "u1", "s1"),
        Product("京东", "kw", "商品A 不同标题", 88.0, 5, "店", 4.5, "u2", "s1"),  # 同 sku
    ]
    out = clean(ps)
    assert len(out) == 1
    assert out[0].price == 88.0 or out[0].price == 99.0  # 任一保留即可


def test_comparator_annotates_and_tags():
    ps = clean([
        Product("京东", "kw", "便宜款", 50.0, 100000, "店", 5.0, "u1", "s1"),
        Product("淘宝", "kw", "贵款", 5000.0, 10, "店", 3.0, "u2", "s2"),
    ])
    annotate(ps)
    assert ps[0].value_score is not None
    assert ps[0].recommend_tag == "全网最低"
    assert ps[1].recommend_tag == "暂不推荐"  # 评分<4


def test_summary_structure():
    ps = clean([
        Product("京东", "kw", "A", 50, 100, "店", 4.5, "u1", "s1"),
        Product("淘宝", "kw", "B", 80, 200, "店", 4.6, "u2", "s2"),
    ])
    annotate(ps)
    s = summary(ps)
    assert s["count"] == 2
    assert s["platform_count"] == 2
    assert s["global_min"] == 50.0
    assert s["cheapest"]["price"] == 50.0


def test_engine_run_full_pipeline():
    engine = CompareEngine()
    r = engine.run("蓝牙耳机", per_platform=5)
    assert r.keyword == "蓝牙耳机"
    assert r.raw_count == 15  # 3 平台 × 5
    assert len(r.products) >= 1
    # 价格升序
    prices = [p.price for p in r.products]
    assert prices == sorted(prices)
    # 图表 HTML 非空
    assert "<div id=" in r.chart_html
    # 每个商品都有性价比分
    assert all(p.value_score is not None for p in r.products)


def test_engine_reproducible():
    """同一关键词多次运行结果一致（确定性）。"""
    e = CompareEngine()
    r1 = e.run("机械键盘", per_platform=4)
    r2 = e.run("机械键盘", per_platform=4)
    assert [p.title for p in r1.products] == [p.title for p in r2.products]
    assert [p.price for p in r1.products] == [p.price for p in r2.products]


def test_engine_empty_keyword_raises():
    import pytest
    try:
        CompareEngine().run("", per_platform=3)
        assert False, "应抛 ValueError"
    except ValueError:
        pass


def test_adapter_registry():
    from price_compare.adapters.registry import get_adapter, list_adapters
    assert len(list_adapters()) >= 3
    ad = get_adapter("jd")
    assert ad.platform == Source.JD.value
    ad2 = get_adapter("淘宝")
    assert ad2.platform == Source.TAOBAO.value


if __name__ == "__main__":
    # 无 pytest 也能跑
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {fn.__name__}: {e}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
