"""命令行工具入口。

用法：
    python -m price_compare.cli <关键词>
    python -m price_compare.cli <关键词> --per-platform 8 --output report.html
    python -m price_compare.cli <关键词> --platforms jd pdd --no-html

支持纯标准库运行（默认输出 HTML 报告到文件 + 终端摘要表格）。
matplotlib 为可选依赖（--png 时使用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List

from .engine import CompareEngine


def _format_table(products) -> str:
    if not products:
        return "（无数据）"
    header = f"{'排名':<4}{'平台':<8}{'价格':>10}{'销量':>10}{'店铺评分':>8}{'性价比':>8}  {'标签':<10}  标题"
    lines = [header, "-" * 90]
    for i, p in enumerate(products, 1):
        tag = p.recommend_tag or "-"
        title = p.title if len(p.title) <= 40 else p.title[:38] + "..."
        lines.append(
            f"{i:<4}{p.platform:<8}¥{p.price:>8.2f}{p.sales:>10}  {p.shop_score:>6.2f}  {p.value_score:>6.1f}  {tag:<10}  {title}"
        )
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="price-compare",
        description="电商商品价格自动化采集与对比工具（京东 / 淘宝 / 拼多多）",
    )
    parser.add_argument("keyword", help="搜索关键词，例如：蓝牙耳机")
    parser.add_argument("--per-platform", type=int, default=10,
                        help="每个平台采集条数（默认 10）")
    parser.add_argument("--platforms", nargs="*", default=None,
                        help="指定平台子集，如 jd taobao pdd；默认三大平台")
    parser.add_argument("--output", "-o", default=None,
                        help="HTML 报告输出路径，默认 <keyword>_report.html")
    parser.add_argument("--json", default=None,
                        help="把清洗后的结果以 JSON 落盘")
    parser.add_argument("--no-html", action="store_true",
                        help="不生成 HTML 报告")
    parser.add_argument("--png", action="store_true",
                        help="额外用 matplotlib 生成 PNG 图表（需安装 matplotlib）")
    args = parser.parse_args(argv)

    if args.platforms:
        engine = CompareEngine.with_platforms(args.platforms)
    else:
        engine = CompareEngine()

    print(f"→ 开始采集关键词：{args.keyword}（每平台 {args.per_platform} 条）")
    result = engine.run(args.keyword, per_platform=args.per_platform)

    print(f"→ 原始采集 {result.raw_count} 条，清洗去重后 {len(result.products)} 条\n")
    print(_format_table(result.products))
    print()

    if result.summary.get("count"):
        s = result.summary
        print("── 跨平台横向摘要 ──")
        print(f"  全网最低价：¥{s['global_min']}   全网最高价：¥{s['global_max']}   均价：¥{s['global_avg']}")
        print(f"  最低价商品：[{s['cheapest']['platform']}] {s['cheapest']['title'][:30]}")
        print(f"  性价比之选：[{s['best_value']['platform']}] {s['best_value']['title'][:30]}（分 {s['best_value']['value_score']}）")
        print(f"  销量冠军  ：[{s['topseller']['platform']}] {s['topseller']['title'][:30]}（{s['topseller']['sales']} 件）")
        print()

    if not args.no_html:
        out_html = args.output or f"{args.keyword}_report.html"
        full_html = _render_full_html(result)
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"→ HTML 报告已生成：{out_html}")

    if args.png:
        from . import visualizer
        out_dir = (args.output or f"{args.keyword}_report").replace(".html", "_charts")
        pngs = visualizer.to_chart_files(result.products, args.keyword, out_dir)
        if pngs:
            print(f"→ PNG 图表已生成：{', '.join(pngs)}")
        else:
            print("→ 未安装 matplotlib，跳过 PNG 生成（可选：pip install matplotlib）")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"→ JSON 结果已落盘：{args.json}")

    return 0


def _render_full_html(result) -> str:
    """生成独立可打开的完整 HTML 报告。"""
    rows = "".join(
        f"""
        <tr>
          <td>{i}</td>
          <td class="plat"><span class="badge {p.platform}">{p.platform}</span></td>
          <td class="price">¥{p.price:.2f}</td>
          <td>{p.sales:,}</td>
          <td>{p.shop_score:.2f}</td>
          <td>{p.value_score:.1f}</td>
          <td>{f'<span class="tag {p.recommend_tag}">{p.recommend_tag}</span>' if p.recommend_tag else '-'}</td>
          <td>{p.trend}</td>
          <td class="title"><a href="{p.url}" target="_blank">{p.title}</a><br><span class="shop">{p.shop_name}</span></td>
        </tr>"""
        for i, p in enumerate(result.products, 1)
    )

    s = result.summary
    platform_cards = "".join(
        f"""<div class="stat-card">
          <div class="stat-plat {ps['platform']}">{ps['platform']}</div>
          <div>条数：{ps['count']}</div>
          <div>最低：¥{ps['min_price']}</div>
          <div>最高：¥{ps['max_price']}</div>
          <div>均价：¥{ps['avg_price']}</div>
          <div>均销量：{ps['avg_sales']:,}</div>
          <div>均评分：{ps['avg_score']}</div>
        </div>"""
        for ps in s.get("platform_stats", [])
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{result.keyword} - 价格对比报告</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; background:#f5f6fa; color:#222; }}
  header {{ background: linear-gradient(135deg,#e1251b 0%,#ff7800 50%,#e02e24 100%); color:#fff; padding: 28px 40px; }}
  header h1 {{ margin:0 0 6px; font-size: 26px; }}
  header .sub {{ opacity: .9; font-size: 14px; }}
  .wrap {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
  .stats {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom: 24px; }}
  .stat-card {{ background:#fff; border-radius:10px; padding:14px 18px; min-width:160px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .stat-card div {{ margin: 3px 0; font-size:13px; }}
  .stat-plat {{ font-weight:700; font-size:16px; margin-bottom:6px; }}
  .stat-plat.京东 {{ color:#e1251b; }}
  .stat-plat.淘宝 {{ color:#ff7800; }}
  .stat-plat.拼多多 {{ color:#e02e24; }}
  .chart-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:24px; }}
  .chart-card {{ background:#fff; border-radius:10px; padding:16px 18px; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .chart-card h3 {{ margin:0 0 8px; font-size:15px; color:#555; }}
  table {{ width:100%; border-collapse:collapse; background:#fff; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); font-size:13px; }}
  th, td {{ padding:9px 10px; text-align:left; border-bottom:1px solid #f0f0f0; vertical-align:top; }}
  th {{ background:#fafafa; color:#666; font-weight:600; position:sticky; top:0; }}
  td.price {{ color:#e1251b; font-weight:700; white-space:nowrap; }}
  td.title a {{ color:#1a73e8; text-decoration:none; }}
  td.title a:hover {{ text-decoration:underline; }}
  .shop {{ font-size:11px; color:#999; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; color:#fff; }}
  .badge.京东 {{ background:#e1251b; }}
  .badge.淘宝 {{ background:#ff7800; }}
  .badge.拼多多 {{ background:#e02e24; }}
  .tag {{ display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; color:#fff; background:#888; }}
  .tag.全网最低 {{ background:#16a34a; }}
  .tag.性价比之选 {{ background:#2563eb; }}
  .tag.销量冠军 {{ background:#9333ea; }}
  .tag.品质优选 {{ background:#0891b2; }}
  .tag.暂不推荐 {{ background:#dc2626; }}
  footer {{ text-align:center; color:#999; padding:20px; font-size:12px; }}
</style>
</head>
<body>
<header>
  <h1>电商商品价格对比报告</h1>
  <div class="sub">关键词：<b>{result.keyword}</b> · 采集 {result.raw_count} 条 → 清洗去重后 {len(result.products)} 条 · 共 {s.get('platform_count',0)} 个平台</div>
</header>
<div class="wrap">
  <div class="stats">{platform_cards}</div>
  {result.chart_html}
  <table>
    <thead><tr><th>排名</th><th>平台</th><th>价格</th><th>销量</th><th>店铺评分</th><th>性价比</th><th>推荐</th><th>趋势</th><th>商品 / 店铺</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<footer>由 price-compare 自动生成 · 数据为演示用模拟数据（与真实平台字段结构一致）</footer>
</body>
</html>"""


if __name__ == "__main__":
    sys.exit(main())
