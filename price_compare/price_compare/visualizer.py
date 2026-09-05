"""可视化：CLI 文本表格 + ASCII 柱状图，以及给前端的 JSON 汇总。"""
from __future__ import annotations

import json
from typing import Any

from .analyzer import analyze
from .models import Product


def render_product_table(products: list[Product], top: int | None = None) -> str:
    """商品清单表格（价格升序）。"""
    rows = products[:top] if top else products
    if not rows:
        return "（无商品）"
    header = ["#", "平台", "商品标题", "价格(¥)", "月销", "店铺", "评分", "来源"]
    widths = [4, 8, 44, 9, 8, 18, 6, 6]
    line = _sep(widths)
    out = [line, _fmt_row(header, widths), line]
    for i, p in enumerate(rows, 1):
        title = p.title if len(p.title) <= 42 else p.title[:41] + "…"
        shop = p.shop if len(p.shop) <= 16 else p.shop[:15] + "…"
        out.append(_fmt_row(
            [str(i), p.platform, title, f"{p.price:.2f}", _fmt_sales(p.sales),
             shop, f"{p.shop_rating:.1f}", p.source],
            widths))
    out.append(line)
    return "\n".join(out)


def render_platform_stats(stats: list[dict]) -> str:
    if not stats:
        return "（无平台数据）"
    header = ["平台", "样本", "最低(¥)", "最高(¥)", "均价(¥)", "中位(¥)", "爆款(月销)"]
    widths = [10, 6, 10, 10, 10, 10, 12]
    line = _sep(widths)
    out = [line, _fmt_row(header, widths), line]
    for s in stats:
        best = s.get("best_seller")
        best_txt = f"{_fmt_sales(best['sales'])} / ¥{best['price']:.0f}" if best else "-"
        out.append(_fmt_row([
            s["platform"], str(s["count"]), f"{s['min_price']:.2f}",
            f"{s['max_price']:.2f}", f"{s['avg_price']:.2f}",
            f"{s['median_price']:.2f}", best_txt], widths))
    out.append(line)
    return "\n".join(out)


def render_value_picks(picks: list[dict]) -> str:
    if not picks:
        return "（无推荐）"
    out = ["★ 性价比推荐 Top3", "-" * 70]
    for p in picks:
        out.append(
            f"  #{p['rank']} [{p['badge']}] {p['platform']}  ¥{p['price']:.2f}  "
            f"月销 {_fmt_sales(p['sales'])}  评分 {p['shop_rating']:.1f}  "
            f"得分 {p['value_score']}")
        out.append(f"     {p['title']}")
    out.append("-" * 70)
    return "\n".join(out)


def render_price_distribution(dist: list[dict]) -> str:
    """ASCII 柱状图：价格区间分布。"""
    if not dist:
        return "（无分布数据）"
    max_count = max((b["count"] for b in dist), default=1) or 1
    bar_w = 40
    out = ["价格区间分布", "-" * 70]
    for b in dist:
        ratio = b["count"] / max_count
        blocks = "█" * int(ratio * bar_w)
        plats = " ".join(f"{k}:{v}" for k, v in b["platforms"].items())
        out.append(f"{b['label']:>16} | {blocks:<{bar_w}} | {b['count']:>3}  {plats}")
    out.append("-" * 70)
    return "\n".join(out)


def render_platform_boxplot(trend: list[dict]) -> str:
    """各平台价格箱线（ASCII）。"""
    if not trend:
        return "（无趋势数据）"
    out = ["各平台价格箱线 (¥)", "-" * 70]
    for t in trend:
        # 把 min..max 映射成 60 个字符
        span = max(t["max"] - t["min"], 1e-6)
        n = 60
        def pos(v: float) -> int:
            return int((v - t["min"]) / span * (n - 1))
        line = [" "] * n
        for i in range(pos(t["q1"]), pos(t["q3"]) + 1):
            line[i] = "▓"
        line[pos(t["median"])] = "│"
        lo, hi = pos(t["min"]), pos(t["max"])
        for i in (lo, hi):
            line[i] = "┃"
        out.append(f"{t['platform']:<6} ¥{t['min']:>7.0f} {''.join(line)} ¥{t['max']:<7.0f}"
                   f"  中位 ¥{t['median']:.0f} (n={t['count']})")
    out.append("-" * 70)
    return "\n".join(out)


def render_full(products: list[Product]) -> str:
    """CLI 完整报告。"""
    analysis = analyze(products)
    sections = [
        _section("商品清单", render_product_table(products)),
        _section("平台横向对比", render_platform_stats(analysis["platform_stats"])),
        _section("性价比推荐", render_value_picks(analysis["value_picks"])),
        _section("价格分布", render_price_distribution(analysis["price_distribution"])),
        _section("价格箱线", render_platform_boxplot(analysis["platform_trend"])),
    ]
    return "\n\n".join(sections)


def to_payload(keyword: str, products: list[Product],
               scraper_stats: list[dict] | None = None) -> dict[str, Any]:
    """给前端的 JSON 汇总。"""
    analysis = analyze(products)
    return {
        "keyword": keyword,
        "total": len(products),
        "products": [p.to_dict() for p in products],
        "platform_stats": analysis["platform_stats"],
        "price_distribution": analysis["price_distribution"],
        "platform_trend": analysis["platform_trend"],
        "value_picks": analysis["value_picks"],
        "scraper_stats": scraper_stats or [],
    }


def to_json_file(payload: dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ---- 辅助 ----------------------------------------------------------
def _sep(widths: list[int]) -> str:
    return "+" + "+".join("-" * (w + 2) for w in widths) + "+"


def _fmt_row(cells: list[str], widths: list[int]) -> str:
    parts = []
    for c, w in zip(cells, widths):
        s = str(c)
        if len(s) > w:
            s = s[: w - 1] + "…"
        parts.append(s.ljust(w))
    return "| " + " | ".join(parts) + " |"


def _fmt_sales(n: int) -> str:
    if n >= 10000:
        return f"{n/10000:.1f}万"
    return str(n)


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}"
