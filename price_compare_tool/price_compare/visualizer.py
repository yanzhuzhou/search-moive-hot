"""可视化方案。

提供两套输出：
1. `to_chart_html(...)`    —— 生成独立 HTML 片段，内嵌 ECharts CDN，
   适合嵌入 Web 演示页或独立打开查看。包含：
     - 价格分布柱状图（按价格升序）
     - 各平台价格区间箱型对比
     - 性价比评分排名横向条形图
     - 销量 vs 价格 散点（气泡大小=评分）
2. `to_chart_files(...)`   —— 可选：matplotlib 静态 PNG，便于 CLI 落盘。

CLI 默认输出 HTML 报告（无外部依赖即可浏览器打开）；matplotlib 为可选。
"""
from __future__ import annotations

import json
import os
from typing import List

from .models import Product


ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"


def _products_to_rows(products: List[Product]) -> List[dict]:
    return [
        {
            "title": p.title,
            "platform": p.platform,
            "price": p.price,
            "sales": p.sales,
            "score": p.shop_score,
            "value": p.value_score or 0,
            "tag": p.recommend_tag or "",
            "trend": p.trend or "",
            "url": p.url,
        }
        for p in products
    ]


def to_chart_html(products: List[Product], keyword: str) -> str:
    """生成包含 4 个 ECharts 图表的独立 HTML 片段（含 div + script）。"""
    rows = _products_to_rows(products)
    data_json = json.dumps(rows, ensure_ascii=False)

    # 截断标题避免 X 轴溢出
    def short(t: str, n: int = 16) -> str:
        return t if len(t) <= n else t[:n] + "..."

    labels = [short(r["title"]) for r in rows]
    prices = [r["price"] for r in rows]
    values = [r["value"] for r in rows]
    sales = [r["sales"] for r in rows]
    scores = [r["score"] for r in rows]
    platforms = [r["platform"] for r in rows]

    # 各平台价格箱型数据
    plat_set = sorted(set(platforms))
    box_data = []
    for plat in plat_set:
        ps = sorted([r["price"] for r in rows if r["platform"] == plat])
        if ps:
            q1 = ps[len(ps) // 4]
            q3 = ps[3 * len(ps) // 4]
            box_data.append({
                "name": plat,
                "min": ps[0],
                "q1": q1,
                "median": ps[len(ps) // 2],
                "q3": q3,
                "max": ps[-1],
            })

    html = f"""
<div class="chart-grid">
  <div class="chart-card">
    <h3>价格分布（升序）</h3>
    <div id="chart-price" style="height:320px;"></div>
  </div>
  <div class="chart-card">
    <h3>各平台价格区间对比</h3>
    <div id="chart-platform" style="height:320px;"></div>
  </div>
  <div class="chart-card">
    <h3>性价比评分排名</h3>
    <div id="chart-value" style="height:320px;"></div>
  </div>
  <div class="chart-card">
    <h3>销量 vs 价格（气泡=评分）</h3>
    <div id="chart-bubble" style="height:320px;"></div>
  </div>
</div>
<script src="{ECHARTS_CDN}"></script>
<script>
(function() {{
  var rows = {data_json};
  var labels = {json.dumps(labels)};
  var prices = {json.dumps(prices)};
  var values = {json.dumps(values)};
  var platforms = {json.dumps(platforms)};
  var platSet = {json.dumps(plat_set)};
  var boxData = {json.dumps(box_data)};

  var colorMap = {{'京东':'#e1251b','淘宝':'#ff7800','拼多多':'#e02e24'}};
  function colorOf(p) {{ return colorMap[p] || '#888'; }}

  // 1. 价格分布
  var c1 = echarts.init(document.getElementById('chart-price'));
  c1.setOption({{
    tooltip: {{ trigger: 'axis', axisPointer: {{type:'shadow'}} }},
    grid: {{ left: 60, right: 20, bottom: 80 }},
    xAxis: {{ type:'category', data: labels, axisLabel: {{rotate:45, interval:0}} }},
    yAxis: {{ type:'value', name:'价格(元)' }},
    series: [{{
      type:'bar',
      data: prices.map(function(v,i){{ return {{value:v, itemStyle:{{color: colorOf(platforms[i])}}}}; }}),
      label: {{ show:true, position:'top', formatter:'{{c}}' }}
    }}]
  }});

  // 2. 平台箱型对比（用箱型近似）
  var c2 = echarts.init(document.getElementById('chart-platform'));
  c2.setOption({{
    tooltip: {{ trigger:'item' }},
    grid: {{ left: 60, right: 20, bottom: 40 }},
    xAxis: {{ type:'category', data: platSet }},
    yAxis: {{ type:'value', name:'价格(元)' }},
    series: [{{
      type:'boxplot',
      data: boxData.map(function(b){{ return [b.min, b.q1, b.median, b.q3, b.max]; }})
    }},
    {{
      type:'scatter',
      symbolSize: 8,
      data: (function() {{
        var arr=[];
        rows.forEach(function(r){{ arr.push([r.platform, r.price]); }});
        return arr;
      }})(),
      itemStyle: {{ color: '#666', opacity: 0.4 }}
    }}]
  }});

  // 3. 性价比评分
  var valuePairs = values.map(function(v,i){{ return [v, labels[i], platforms[i]]; }});
  valuePairs.sort(function(a,b){{ return b[0]-a[0]; }});
  var c3 = echarts.init(document.getElementById('chart-value'));
  c3.setOption({{
    tooltip: {{ trigger:'axis', axisPointer: {{type:'shadow'}} }},
    grid: {{ left: 120, right: 30, bottom: 20 }},
    xAxis: {{ type:'value', max: 100, name:'性价比分' }},
    yAxis: {{ type:'category', data: valuePairs.map(function(x){{return x[1];}}) }},
    series: [{{
      type:'bar',
      data: valuePairs.map(function(x){{ return {{value:x[0], itemStyle:{{color: x[0]>=70?'#22c55e': (x[0]>=50?'#f59e0b':'#ef4444')}}}}; }}),
      label: {{ show:true, position:'right', formatter:'{{c}}' }}
    }}]
  }});

  // 4. 气泡图：销量 vs 价格
  var c4 = echarts.init(document.getElementById('chart-bubble'));
  c4.setOption({{
    tooltip: {{
      trigger:'item',
      formatter: function(p) {{
        return p.data[3] + '<br/>价格:¥'+p.data[1]+'<br/>销量:'+p.data[0]+'<br/>评分:'+p.data[2];
      }}
    }},
    grid: {{ left: 70, right: 20, bottom: 50 }},
    xAxis: {{ type:'value', name:'价格(元)' }},
    yAxis: {{ type:'value', name:'销量(件)' }},
    series: [{{
      type:'scatter',
      data: rows.map(function(r){{ return [r.sales, r.price, r.score, r.title, r.platform]; }}).map(function(x){{ return [x[0],x[1],x[2],x[3]]; }}),
      symbolSize: function(v){{ return Math.max(8, v[2]*8); }},
      itemStyle: {{ color: function(p){{ return colorOf(rows[p.dataIndex].platform); }}, opacity:0.75 }},
      label: {{ show:false }}
    }}]
  }});

  window.addEventListener('resize', function() {{
    [c1,c2,c3,c4].forEach(function(c){{ c.resize(); }});
  }});
}})();
</script>
"""
    return html


def to_chart_files(products: List[Product], keyword: str, out_dir: str) -> List[str]:
    """可选：用 matplotlib 生成静态 PNG 图。需 matplotlib 已安装。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    os.makedirs(out_dir, exist_ok=True)
    saved = []

    # 价格升序柱状
    fig, ax = plt.subplots(figsize=(10, 4))
    sorted_p = sorted(products, key=lambda x: x.price)
    ax.bar(range(len(sorted_p)), [p.price for p in sorted_p],
           color=[{"京东": "#e1251b", "淘宝": "#ff7800", "拼多多": "#e02e24"}.get(p.platform, "#888") for p in sorted_p])
    ax.set_ylabel("价格(元)")
    ax.set_title(f"{keyword} 价格分布（升序）")
    p1 = os.path.join(out_dir, "price_distribution.png")
    fig.savefig(p1, bbox_inches="tight"); plt.close(fig); saved.append(p1)

    # 性价比评分
    fig, ax = plt.subplots(figsize=(10, 4))
    sv = sorted(products, key=lambda x: -(x.value_score or 0))
    ax.barh(range(len(sv)), [p.value_score or 0 for p in sv],
            color=["#22c55e" if (p.value_score or 0) >= 70 else "#f59e0b" if (p.value_score or 0) >= 50 else "#ef4444" for p in sv])
    ax.set_xlabel("性价比分")
    ax.set_title(f"{keyword} 性价比评分排名")
    p2 = os.path.join(out_dir, "value_score.png")
    fig.savefig(p2, bbox_inches="tight"); plt.close(fig); saved.append(p2)

    return saved
