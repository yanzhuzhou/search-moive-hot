"""命令行工具入口。

用法：
    python -m price_compare.cli search <关键词> [options]
    python -m price_compare.cli report <json文件>      # 从已保存结果出报告

示例：
    python -m price_compare.cli search 无线鼠标 --limit 18 --json result.json
    python -m price_compare.cli report result.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from . import __version__
from .models import Platform, Product
from .processor import process
from .scrapers import JDScraper, TaobaoScraper, PinduoduoScraper
from .visualizer import render_full, to_payload, to_json_file


def _build_scrapers(platforms: list[str], real: bool, cookie_tb: str):
    """按需实例化采集器。"""
    scrapers = []
    if "jd" in platforms:
        scrapers.append(JDScraper(allow_real=real))
    if "taobao" in platforms:
        scrapers.append(TaobaoScraper(allow_real=real, cookie=cookie_tb))
    if "pinduoduo" in platforms:
        scrapers.append(PinduoduoScraper(allow_real=real))
    return scrapers


def run_search(keyword: str, limit: int = 20, platforms: list[str] | None = None,
                real: bool = False, cookie_tb: str = "") -> dict[str, Any]:
    """执行一次完整搜索：采集 → 清洗去重 → 分析 → 返回 payload。

    real=False 时所有采集器使用演示数据（默认），real=True 时尝试真实抓取。
    """
    platforms = platforms or ["jd", "taobao", "pinduoduo"]
    scrapers = _build_scrapers(platforms, real, cookie_tb)

    raw: list[Product] = []
    scraper_stats: list[dict] = []
    per_platform_limit = max(1, limit // len(scrapers)) if scrapers else 0
    for s in scrapers:
        items = s.search(keyword, limit=per_platform_limit)
        raw.extend(items)
        scraper_stats.append({
            "name": s.name, "platform": s.platform_cn, **s.stats})

    products = process(raw)
    payload = to_payload(keyword, products, scraper_stats=scraper_stats)
    return payload


def cmd_search(args: argparse.Namespace) -> int:
    payload = run_search(
        keyword=args.keyword, limit=args.limit, platforms=args.platforms,
        real=args.real, cookie_tb=args.taobao_cookie)
    # 控制台报告
    products = [Product.from_dict(p) for p in payload["products"]]
    print(render_full(products))
    print("\n采集统计：")
    for s in payload["scraper_stats"]:
        print(f"  - {s['platform']:<5} 来源={s['source']:<5} "
              f"real={s['real_count']} demo={s['demo_count']} "
              f"耗时={s['elapsed_ms']}ms")
    if args.json:
        to_json_file(payload, args.json)
        print(f"\n结果已保存到 {args.json}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    with open(args.file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    products = [Product.from_dict(p) for p in payload["products"]]
    print(render_full(products))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="price_compare",
        description="电商商品价格自动化采集与对比工具 (京东/淘宝/拼多多)",
    )
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("search", help="按关键词采集并对比")
    sp.add_argument("keyword", help="搜索关键词，如 无线鼠标")
    sp.add_argument("-n", "--limit", type=int, default=24, help="每个平台采集条数上限")
    sp.add_argument("-p", "--platforms", default="jd,taobao,pinduoduo",
                    help="平台列表，逗号分隔，如 jd,taobao")
    sp.add_argument("--real", action="store_true",
                    help="尝试真实抓取（默认关闭，使用演示数据；真实抓取可能被反爬拦截）")
    sp.add_argument("--taobao-cookie", default="", help="淘宝登录态 cookie（--real 时有效）")
    sp.add_argument("--json", help="结果保存到 JSON 文件路径")
    sp.set_defaults(func=cmd_search, platforms=None)

    rp = sub.add_parser("report", help="从已保存的 JSON 文件出报告")
    rp.add_argument("file", help="JSON 结果文件路径")
    rp.set_defaults(func=cmd_report)
    return p


def _normalize(args: argparse.Namespace) -> None:
    if getattr(args, "keyword", None) is not None:
        raw = getattr(args, "platforms", None)
        if raw is None:
            args.platforms = ["jd", "taobao", "pinduoduo"]
        elif isinstance(raw, str):
            args.platforms = [p.strip() for p in raw.split(",") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    _normalize(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
