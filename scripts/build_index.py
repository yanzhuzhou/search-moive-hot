#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""把 style.css + echarts.min.js + data/data.js + app.js
内联进单一的 index.html（双击即可打开，零依赖）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()

css = read("style.css")
echarts = read("echarts.min.js")
data_js = read("data/data.js")          # window.BOXDATA = {...};
app = read("app.js")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>国内电影票房数据分析 · 在映 / 年度双榜看板</title>
<style>
{css}
</style>
</head>
<body>
<header class="site-header">
  <div class="wrap">
    <h1>国内电影票房数据分析</h1>
    <p class="subtitle">三源融合 · 在映前十 · 年度近似 · 城市/院线/影院 · 七日趋势 · 影片检索对比</p>
    <p class="meta" id="meta">数据加载中…</p>
  </div>
</header>

<div class="wrap">
  <div class="disclaimer" id="disclaimer"></div>

  <div class="realtime-bar" id="realtimeBar"></div>

  <div class="tabs">
    <div class="tab active" data-view="viewShowing">🎬 在映前十票房</div>
    <div class="tab" data-view="viewYearly">🏆 年度前十（近似）</div>
    <div class="tab" data-view="viewInsight">📊 市场洞察</div>
  </div>

  <!-- 在映前十 -->
  <section class="view active" id="viewShowing">
    <section class="panel">
      <h2>📊 在映影片票房 TOP10 <span class="tag">实时</span></h2>
      <div id="showBar" class="chart"></div>
      <div class="table-wrap">
        <table id="showTable">
          <thead><tr><th>排名</th><th>影片</th><th>当日票房</th><th>累计票房</th>
            <th>占比</th><th>排片</th><th>上座</th><th>人次</th><th>上映</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>🗺️ 票房分布 TOP10</h2>
      <div class="dist-stack">
        <div class="dist-item">
          <h3>🏙️ 城市票房 TOP10</h3>
          <div id="cityChart" class="chart"></div>
        </div>
        <div class="dist-item">
          <h3>🏢 院线票房 TOP10</h3>
          <div id="chainChart" class="chart"></div>
        </div>
        <div class="dist-item">
          <h3>🎬 影院票房 TOP10</h3>
          <div id="cinemaChart" class="chart"></div>
        </div>
      </div>
    </section>
  </section>

  <!-- 年度前十 -->
  <section class="view" id="viewYearly">
    <section class="panel">
      <h2>🏆 年度票房前十（在映累计近似） <span class="tag">近似</span></h2>
      <div class="note" id="yearlyNote"></div>
      <div id="yearBar" class="chart"></div>
      <div class="table-wrap">
        <table id="yearTable">
          <thead><tr><th>排名</th><th>影片</th><th>累计总票房</th><th>当日票房</th><th>上映</th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </section>
  </section>

  <!-- 市场洞察 -->
  <section class="view" id="viewInsight">
    <section class="panel">
      <h2>📈 近 7 日大盘走势 <span class="tag">每日</span></h2>
      <div id="weeklyNote"></div>
      <div id="weeklyChart" class="chart"></div>
    </section>
    <section class="panel">
      <h2>🎯 排片率 · 上座率 · 票房</h2>
      <div class="note">横轴=排片率，纵轴=上座率，气泡大小=当日票房。右上角「高排片+高上座」通常是爆款信号。</div>
      <div id="scatterChart" class="chart"></div>
    </section>
    <section class="panel">
      <h2>🎭 影片类型分布（按当日票房）</h2>
      <div class="note">跨类型影片按各标签拆分计入，合计可能超过大盘；反映当日题材结构。</div>
      <div id="genreChart" class="chart"></div>
    </section>
  </section>

  <!-- 检索对比 -->
  <section class="panel">
    <h2>🔍 影片检索、评分对比与简介</h2>
    <div id="clickHint" class="note">💡 点击上方榜单（在映 / 年度）中的任意影片，即可在此查看其
      <b>豆瓣 · 猫眼 · 淘票票 · TMDB</b> 多平台评分对比与影片简介；也可在下方输入框按片名检索。</div>
    <div class="controls">
      <input id="searchInput" type="text" placeholder="输入影片名，如：欢迎来龙餐馆" />
      <button id="searchBtn">查询并对比</button>
    </div>
    <div id="searchHint" class="note hidden">输入影片名后，展示该片档案（海报/类型/上映日/累计·当日票房/占比/排片/上座/人次），并与在映前十做累计+当日双维度对比。</div>
    <div id="movieProfile" class="profile-card hidden"></div>
    <div class="detail-charts" id="detailChartsWrap">
      <div id="ratingsChart" class="chart sm hidden"></div>
      <div id="compareDayWrap" class="hidden"><div id="compareDayChart" class="chart sm"></div></div>
      <div id="compareChart" class="chart full-width hidden"></div>
    </div>
    <div id="compareTrendChart" class="chart hidden"></div>
  </section>

  <footer class="site-footer">
    <p>本看板为开源数据分析示例，数据来自公开接口（中影票房网 / 猫眼专业版），不构成任何投资或商业建议。</p>
  </footer>
</div>

<script>{echarts}</script>
<script>{data_js}</script>
<script>{app}</script>
</body>
</html>"""

with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)

print("✅ 已生成自包含 index.html  (%.0f KB)" % (len(html.encode("utf-8")) / 1024))
