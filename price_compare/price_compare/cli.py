"""命令行工具入口。

用法：
    python -m price_compare.cli search <关键词> [options]
    python -m price_compare.cli login <jd|taobao|pinduoduo>   # 引导 Playwright 登录
    python -m price_compare.cli report <json文件>             # 从已保存结果出报告

示例：
    # 演示模式（最稳，不依赖真实采集）
    python -m price_compare.cli search 无线鼠标

    # Playwright 真实采集（需先 login 一次）
    python -m price_compare.cli login jd
    python -m price_compare.cli search 无线鼠标 --scraper playwright --real

    # 原生 requests 真实采集（京东/淘宝需 cookie，拼多多需 anti_content）
    python -m price_compare.cli search 无线鼠标 --real --taobao-cookie "xxx"

    # 保存结果 + 重新出报告
    python -m price_compare.cli search 无线鼠标 --json result.json
    python -m price_compare.cli report result.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from . import __version__
from .models import Product
from .processor import process
from .scrapers import make_scraper
from .visualizer import render_full, to_payload, to_json_file


def run_search(keyword: str, limit: int = 24,
               platforms: list[str] | None = None,
               scraper_type: str = "requests",
               real: bool = False,
               taobao_cookie: str = "",
               pdd_anti_content: str = "") -> dict[str, Any]:
    """执行一次完整搜索。

    Args:
        keyword: 搜索关键词
        limit: 每个平台采集条数
        platforms: 平台列表
        scraper_type: "requests" (默认 urllib) / "playwright" (浏览器)
        real: 是否尝试真实抓取（real=False 时全部回退演示数据）
        taobao_cookie / pdd_anti_content: 原生 requests 模式需要的认证参数
    """
    platforms = platforms or ["jd", "taobao", "pinduoduo"]
    scrapers = [
        make_scraper(p, scraper_type=scraper_type,
                     allow_real=real,
                     taobao_cookie=taobao_cookie,
                     pdd_anti_content=pdd_anti_content)
        for p in platforms
    ]

    raw: list[Product] = []
    scraper_stats: list[dict] = []
    per_platform_limit = max(1, limit // len(scrapers)) if scrapers else 0
    for s in scrapers:
        items = s.search(keyword, limit=per_platform_limit)
        raw.extend(items)
        scraper_stats.append({
            "name": s.name, "platform": s.platform_cn,
            "scraper_type": scraper_type, **s.stats})

    products = process(raw)
    payload = to_payload(keyword, products, scraper_stats=scraper_stats)
    payload["scraper_type"] = scraper_type
    return payload


def cmd_search(args: argparse.Namespace) -> int:
    payload = run_search(
        keyword=args.keyword, limit=args.limit, platforms=args.platforms,
        scraper_type=args.scraper, real=args.real,
        taobao_cookie=args.taobao_cookie, pdd_anti_content=args.pdd_anti_content)
    products = [Product.from_dict(p) for p in payload["products"]]
    print(render_full(products))
    print("\n采集统计（scraper=%s）：" % payload.get("scraper_type", "requests"))
    for s in payload["scraper_stats"]:
        print(f"  - {s['platform']:<5} 来源={s['source']:<5} "
              f"real={s['real_count']} demo={s['demo_count']} "
              f"耗时={s['elapsed_ms']}ms")
    if args.json:
        to_json_file(payload, args.json)
        print(f"\n结果已保存到 {args.json}")
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Playwright 登录引导。"""
    try:
        from .scrapers.playwright_scrapers import (
            login_interactive, close_browser, playwright_available,
        )
    except ImportError:
        print("Playwright 未安装。请先执行:")
        print("  pip install playwright && playwright install chromium")
        return 1
    if not playwright_available():
        print("Playwright Python 包未安装。请先执行:")
        print("  pip install playwright && playwright install chromium")
        return 1

    platform_map = {
        "jd": ("京东", "https://passport.jd.com/new/login.aspx"),
        "taobao": ("淘宝", "https://login.taobao.com/member/login.htm"),
        "pinduoduo": ("拼多多", "https://mobile.yangkeduo.com/login.html"),
    }
    key = args.platform
    if key not in platform_map:
        print(f"未知平台 {key}，可选: {list(platform_map.keys())}")
        return 1
    cn, url = platform_map[key]
    ok = login_interactive(cn, url)
    if ok:
        print(f"\n✓ {cn} cookie 已保存。现在可以运行:")
        print(f"  python -m price_compare.cli search 关键词 --scraper playwright --real")
    close_browser()
    return 0 if ok else 1


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
    sp.add_argument("--scraper", choices=["requests", "playwright"], default="requests",
                    help="采集器类型：requests(urllib，默认) / playwright(浏览器，需先 login)")
    sp.add_argument("--real", action="store_true",
                    help="尝试真实抓取（默认关闭，使用演示数据）")
    sp.add_argument("--taobao-cookie", default="", help="淘宝登录态 cookie（requests 模式 --real 时有效）")
    sp.add_argument("--pdd-anti-content", default="",
                    help="拼多多 anti_content 风控参数（requests 模式 --real 时有效）")
    sp.add_argument("--json", help="结果保存到 JSON 文件路径")
    sp.set_defaults(func=cmd_search, platforms=None)

    lp = sub.add_parser("login", help="Playwright 首次登录引导（保存 cookie）")
    lp.add_argument("platform", choices=["jd", "taobao", "pinduoduo"],
                    help="要登录的平台")
    lp.set_defaults(func=cmd_login)

    rp = sub.add_parser("report", help="从已保存的 JSON 文件出报告")
    rp.add_argument("file", help="JSON 结果文件路径")
    rp.set_defaults(func=cmd_report)
    return p


def _normalize(args: argparse.Namespace) -> None:
    raw = getattr(args, "platforms", None)
    if raw is None or isinstance(raw, str):
        args.platforms = ["jd", "taobao", "pinduoduo"] if raw is None else \
            [p.strip() for p in raw.split(",") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    _normalize(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
