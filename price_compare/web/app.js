"use strict";

const PLATFORM_COLOR = { "京东": "#E4393C", "淘宝": "#FF5000", "拼多多": "#E02E24" };
const PLATFORM_KEY = { jd: "京东", taobao: "淘宝", pinduoduo: "拼多多" };

const $ = (id) => document.getElementById(id);

let distChart, boxChart;
let currentFilter = "all";
let currentPayload = null;
let pwStatus = { playwright_available: false, logged_in_platforms: [] };

document.addEventListener("DOMContentLoaded", () => {
  distChart = echarts.init($("distChart"));
  boxChart = echarts.init($("boxChart"));
  window.addEventListener("resize", () => { distChart.resize(); boxChart.resize(); });

  // 平台 chip 切换
  document.querySelectorAll(".platform-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const cb = chip.querySelector("input");
      cb.checked = !cb.checked;
      chip.classList.toggle("on", cb.checked);
    });
  });

  $("runBtn").addEventListener("click", onRun);
  $("resetBtn").addEventListener("click", onReset);
  $("keyword").addEventListener("keydown", (e) => { if (e.key === "Enter") onRun(); });

  // 并行拉 demo + health
  Promise.all([fetch("/api/demo").then(r => r.json()),
               fetch("/api/health").then(r => r.json())])
    .then(([demo, health]) => {
      pwStatus = health.scraper || {};
      renderHealth();
      $("keyword").value = demo.keyword;
      renderPayload(demo.result);
    })
    .catch((e) => showError("加载失败: " + e.message));
});

function openLoginGuide() { $("loginModal").classList.remove("hidden"); }

function renderHealth() {
  const el = $("pwStatus");
  if (pwStatus.playwright_available) {
    el.innerHTML = "✓ Playwright 可用" +
      (pwStatus.logged_in_platforms.length
        ? " · 已登录: " + pwStatus.logged_in_platforms.join(" / ")
        : " · 未登录（演示数据）");
    el.style.color = pwStatus.logged_in_platforms.length ? "var(--green)" : "var(--amber)";
  } else {
    el.innerHTML = "⚠ Playwright 未安装（当前仅演示数据）";
    el.style.color = "var(--amber)";
  }

  // 登录引导条
  const bar = $("loginBar");
  const selectedScraper = document.querySelector('input[name="scraper"]:checked').value;
  if (selectedScraper === "playwright") {
    if (!pwStatus.playwright_available) {
      bar.classList.remove("hidden");
      bar.classList.remove("ok");
      $("loginBarText").innerHTML = "<b>Playwright 未安装</b>。需要先执行 <code>pip install playwright && playwright install chromium</code>。";
    } else if (pwStatus.logged_in_platforms.length === 0) {
      bar.classList.remove("hidden");
      bar.classList.remove("ok");
      $("loginBarText").innerHTML = "<b>Playwright 已安装但未登录</b>。请先在终端执行 <code>python -m price_compare.cli login jd</code> 登录一次。";
    } else {
      bar.classList.remove("hidden");
      bar.classList.add("ok");
      $("loginBarText").innerHTML = "<b>✓ Playwright 就绪</b>。已登录: " + pwStatus.logged_in_platforms.join(" / ") + "，开始采集将使用真实浏览器抓取。";
    }
  } else {
    bar.classList.add("hidden");
  }
}

async function onRun() {
  const keyword = $("keyword").value.trim();
  if (!keyword) { showError("请输入关键词"); return; }
  const platforms = [...document.querySelectorAll(".platform-chip.on")]
    .map(c => c.dataset.pf).filter(p => PLATFORM_KEY[p]);
  if (!platforms.length) { showError("请至少选一个平台"); return; }
  const limit = parseInt($("limit").value, 10) || 8;
  const scraper = document.querySelector('input[name="scraper"]:checked').value;
  const real = $("realToggle").checked;

  setLoading(true, "正在采集 " + keyword + "…");
  $("runBtn").disabled = true;
  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keyword, platforms, limit, scraper, real }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || ("HTTP " + resp.status));
    renderPayload(data);
  } catch (e) {
    showError("采集失败: " + e.message);
  } finally {
    setLoading(false);
    $("runBtn").disabled = false;
  }
}

function onReset() {
  fetch("/api/demo").then(r => r.json()).then(d => {
    $("keyword").value = d.keyword;
    renderPayload(d.result);
  });
}

function renderPayload(payload) {
  currentPayload = payload;
  currentFilter = "all";
  renderStats(payload);
  renderDistribution(payload.price_distribution);
  renderBox(payload.platform_trend);
  renderPicks(payload.value_picks);
  renderPlatformStats(payload.platform_stats);
  renderFilterBar(payload);
  renderTable(payload.products);
  renderScrapers(payload.scraper_stats);
}

function renderStats(p) {
  const products = p.products || [];
  const prices = products.map(x => x.price);
  const minP = prices.length ? Math.min(...prices) : 0;
  const maxP = prices.length ? Math.max(...prices) : 0;
  const cheapest = prices.length ? products[0] : null;
  const nReal = products.filter(x => x.source === "real").length;
  const stats = [
    { label: "商品总数", value: p.total || products.length, sub: `${p.keyword || ""}` },
    { label: "真实数据", value: nReal, sub: nReal ? `${Math.round(nReal / (p.total || 1) * 100)}% of total` : "演示数据" },
    { label: "平台数", value: new Set(products.map(x => x.platform)).size,
      sub: [...new Set(products.map(x => x.platform))].join(" · ") },
    { label: "最低价", value: `¥${minP.toFixed(2)}`,
      sub: cheapest ? `${pfLabel(cheapest.platform)} · ${shortTitle(cheapest.title, 16)}` : "-" },
    { label: "最高销量", value: fmtSales(Math.max(...products.map(x => x.sales), 0)), sub: "月销" },
    { label: "性价比 Top1", value: p.value_picks[0] ? `¥${p.value_picks[0].price.toFixed(0)}` : "-",
      sub: p.value_picks[0] ? p.value_picks[0].platform : "-" },
  ];
  $("stats").innerHTML = stats.map(s => `
    <div class="stat">
      <div class="label">${s.label}</div>
      <div class="value">${s.value}</div>
      <div class="sub">${s.sub}</div>
    </div>`).join("");
}

function renderDistribution(dist) {
  if (!dist || !dist.length) { distChart.clear(); return; }
  const labels = dist.map(d => d.label);
  const series = {};
  dist.forEach(d => {
    Object.entries(d.platforms || {}).forEach(([pf, cnt]) => {
      (series[pf] = series[pf] || {})[d.label] = cnt;
    });
  });
  const ser = Object.entries(series).map(([pf, vals]) => ({
    name: pf, type: "bar", stack: "total", emphasis: { focus: "series" },
    itemStyle: { color: PLATFORM_COLOR[pf] || "#888", borderRadius: [3,3,0,0] },
    data: labels.map(l => vals[l] || 0),
  }));
  distChart.setOption({
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, textStyle: { color: "#6b7280" } },
    grid: { left: 50, right: 20, top: 36, bottom: 40 },
    xAxis: { type: "category", data: labels,
             axisLabel: { color: "#9ca3af", fontSize: 11 },
             axisLine: { lineStyle: { color: "#e5e8ec" } } },
    yAxis: { type: "value", axisLabel: { color: "#9ca3af" },
             splitLine: { lineStyle: { color: "#eef1f4" } } },
    series: ser,
  }, true);
}

function renderBox(trend) {
  if (!trend || !trend.length) { boxChart.clear(); return; }
  boxChart.setOption({
    tooltip: { trigger: "item", formatter: p => p.name },
    legend: { top: 0, textStyle: { color: "#6b7280" } },
    grid: { left: 70, right: 20, top: 36, bottom: 30 },
    xAxis: { type: "category", data: trend.map(t => t.platform),
             axisLabel: { color: "#6b7280" },
             axisLine: { lineStyle: { color: "#e5e8ec" } } },
    yAxis: { type: "value", name: "价格 ¥", nameTextStyle: { color: "#9ca3af" },
             axisLabel: { color: "#9ca3af" },
             splitLine: { lineStyle: { color: "#eef1f4" } } },
    series: [{
      name: "价格箱线", type: "boxplot",
      data: trend.map(t => [t.min, t.q1, t.median, t.q3, t.max]),
      itemStyle: { borderColor: "#2563eb", color: "rgba(37,99,235,.15)" },
    }, {
      name: "样本数", type: "scatter", symbolSize: 0,
      data: trend.map((t, i) => [i, t.max]),
      label: { show: true, formatter: p => "n=" + trend[p.dataIndex].count,
               color: "#9ca3af", position: "top", fontSize: 11 },
    }],
  }, true);
}

function renderPicks(picks) {
  if (!picks || !picks.length) {
    $("picks").innerHTML = '<div style="color:var(--text-subtle);padding:20px;">暂无数据</div>';
    return;
  }
  $("picks").innerHTML = picks.map((p, i) => `
    <div class="pick ${i === 0 ? "top1" : ""}">
      <span class="rank">#${p.rank}</span>
      <div class="title">${escapeHtml(p.title)}</div>
      <div class="price">¥${p.price.toFixed(2)}
        ${p.badge ? `<span class="badge">${p.badge}</span>` : ""}</div>
      <div class="meta">
        <span style="color:${PLATFORM_COLOR[p.platform]};font-weight:600;">${p.platform}</span>
        <span>月销 ${fmtSales(p.sales)}</span>
        <span>评分 ${p.shop_rating}</span>
        <span>得分 ${p.value_score}</span>
      </div>
    </div>`).join("");
}

function renderPlatformStats(stats) {
  if (!stats || !stats.length) { $("platformStats").innerHTML = "暂无数据"; return; }
  $("platformStats").innerHTML = `
  <table class="comp-table">
    <tr>
      <th>平台</th><th>样本</th><th>最低</th><th>最高</th><th>均价</th><th>中位</th><th>爆款</th>
    </tr>
    ${stats.map(s => `
    <tr>
      <td><span class="pf-badge pf-${pfKey(s.platform)}"><span class="dot"></span>${s.platform}</span></td>
      <td>${s.count}</td>
      <td style="color:var(--green);font-weight:600;">¥${s.min_price.toFixed(2)}</td>
      <td>¥${s.max_price.toFixed(2)}</td>
      <td>¥${s.avg_price.toFixed(2)}</td>
      <td>¥${s.median_price.toFixed(2)}</td>
      <td>${s.best_seller ? `${fmtSales(s.best_seller.sales)} / ¥${s.best_seller.price.toFixed(0)}` : "-"}</td>
    </tr>`).join("")}
  </table>`;
}

function renderFilterBar(payload) {
  const platforms = [...new Set(payload.products.map(p => p.platform))];
  const tags = ["全部", ...platforms];
  $("filterBar").innerHTML = tags.map(t =>
    `<span class="tag-filter ${t === currentFilter ? "active" : ""}" data-pf="${t}">${t}</span>`
  ).join("");
  $("filterBar").querySelectorAll(".tag-filter").forEach(el => {
    el.addEventListener("click", () => {
      currentFilter = el.dataset.pf;
      renderFilterBar(payload);
      renderTable(payload.products);
    });
  });
}

function renderTable(products) {
  const filtered = currentFilter === "all" ? products
    : products.filter(p => p.platform === currentFilter);
  $("tableHint").textContent = `— 按价格升序 · 共 ${filtered.length} 条` +
    (currentFilter !== "all" ? ` · 仅 ${currentFilter}` : "");
  $("productTbody").innerHTML = filtered.map((p, i) => `
    <tr>
      <td class="col-num">${i + 1}</td>
      <td><span class="pf-badge pf-${pfKey(p.platform)}"><span class="dot"></span>${p.platform}</span></td>
      <td class="title" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</td>
      <td class="col-price price-cell">¥${p.price.toFixed(2)}</td>
      <td>${fmtSales(p.sales)}</td>
      <td title="${escapeHtml(p.shop)}">${escapeHtml(p.shop)}</td>
      <td>${p.shop_rating}</td>
      <td><span class="src-badge src-${p.source}">${p.source === "demo" ? "演示" : "真实"}</span></td>
      <td class="col-link"><a class="link-btn" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">查看</a></td>
    </tr>`).join("");
}

function renderScrapers(scrapers) {
  if (!scrapers || !scrapers.length) { $("scrapers").innerHTML = "-"; return; }
  $("scrapers").innerHTML = scrapers.map(s => {
    const ok = s.source === "real";
    return `<div class="scraper-card">
      <b>${s.platform}</b>
      · ${ok ? '<span style="color:var(--green)">✓ 真实</span>' : '<span style="color:var(--amber)">演示</span>'}
      · ${s.scraper_type || "requests"}
      · ${s.elapsed_ms}ms
      · real=${s.real_count} demo=${s.demo_count}
    </div>`;
  }).join("");
}

// ---- helpers ----
function setLoading(loading, msg) { document.body.style.cursor = loading ? "wait" : ""; }
function showError(msg) {
  const old = document.querySelector(".error-box"); if (old) old.remove();
  const box = document.createElement("div");
  box.className = "error-box"; box.textContent = msg;
  document.querySelector(".page").prepend(box);
  setTimeout(() => box.remove(), 8000);
}
function fmtSales(n) { n = Number(n) || 0; return n >= 10000 ? (n / 10000).toFixed(1) + "万" : String(n); }
function shortTitle(t, n) { return t.length > n ? t.slice(0, n - 1) + "…" : t; }
function pfLabel(name) { return PLATFORM_KEY[pfKey(name)] || name; }
function pfKey(name) {
  return Object.entries(PLATFORM_KEY).find(([, v]) => v === name)?.[0] || "";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[c]);
}
