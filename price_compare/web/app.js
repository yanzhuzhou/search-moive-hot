"use strict";

const PLATFORM_COLOR = {
    "京东": "#e62129", "淘宝": "#ff7400", "拼多多": "#e1251b",
};
const PLATFORM_KEY = { jd: "京东", taobao: "淘宝", pinduoduo: "拼多多" };

const $ = (id) => document.getElementById(id);

let distChart = null;
let boxChart = null;
let currentFilter = "all";
let currentPayload = null;

// ---- 初始化 ----------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    distChart = echarts.init($("distChart"));
    boxChart = echarts.init($("boxChart"));
    window.addEventListener("resize", () => {
        distChart.resize(); boxChart.resize();
    });

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
    $("keyword").addEventListener("keydown", (e) => {
        if (e.key === "Enter") onRun();
    });

    // 载入示例数据
    loadDemo();
});

async function loadDemo() {
    setLoading(true, "载入示例数据…");
    try {
        const resp = await fetch("/api/demo");
        const data = await resp.json();
        $("keyword").value = data.keyword;
        renderPayload(data.result);
        bannerUpdate(data.result);
    } catch (e) {
        showError("载入示例失败: " + e.message);
    } finally {
        setLoading(false);
    }
}

async function onRun() {
    const keyword = $("keyword").value.trim();
    if (!keyword) { showError("请输入关键词"); return; }
    const platforms = [...document.querySelectorAll(".platform-chip.on")]
        .map((c) => c.dataset.pf).filter((p) => PLATFORM_KEY[p]);
    if (platforms.length === 0) { showError("请至少选择一个平台"); return; }
    const limit = parseInt($("limit").value, 10) || 8;
    const real = $("realToggle").checked;

    setLoading(true, "正在采集 " + keyword + "…");
    $("runBtn").disabled = true;
    try {
        const resp = await fetch("/api/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keyword, platforms, limit, real }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.error || ("HTTP " + resp.status));
        }
        renderPayload(data);
        bannerUpdate(data);
    } catch (e) {
        showError("采集失败: " + e.message);
    } finally {
        setLoading(false);
        $("runBtn").disabled = false;
    }
}

function onReset() { loadDemo(); }

// ---- 渲染 ------------------------------------------------------------
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
    const prices = products.map((x) => x.price);
    const minP = prices.length ? Math.min(...prices) : 0;
    const maxP = prices.length ? Math.max(...prices) : 0;
    const cheapest = prices.length ? products[0] : null;
    const stats = [
        { label: "商品总数", value: p.total || products.length,
          sub: `${p.keyword || ""}` },
        { label: "覆盖平台", value: new Set(products.map((x) => x.platform)).size,
          sub: [...new Set(products.map((x) => x.platform))].join(" / ") || "-" },
        { label: "价格区间", value: `¥${minP.toFixed(0)} ~ ¥${maxP.toFixed(0)}`,
          sub: `跨度 ¥${(maxP - minP).toFixed(0)}` },
        { label: "最低价", value: `¥${minP.toFixed(2)}`,
          sub: cheapest ? `${cheapest.platform} · ${shortTitle(cheapest.title, 16)}` : "-" },
        { label: "最高销量", value: fmtSales(Math.max(...products.map((x) => x.sales), 0)),
          sub: "月销" },
        { label: "性价比 Top1", value: (p.value_picks[0] ? `¥${p.value_picks[0].price.toFixed(0)}` : "-"),
          sub: (p.value_picks[0] ? p.value_picks[0].platform : "-") },
    ];
    $("stats").innerHTML = stats.map((s) => `
        <div class="stat">
            <div class="label">${s.label}</div>
            <div class="value">${s.value}</div>
            <div class="sub">${s.sub}</div>
        </div>`).join("");
}

function renderDistribution(dist) {
    if (!dist || !dist.length) { distChart.clear(); return; }
    const labels = dist.map((d) => d.label);
    const series = {};
    dist.forEach((d) => {
        Object.entries(d.platforms || {}).forEach(([pf, cnt]) => {
            (series[pf] = series[pf] || {})[d.label] = cnt;
        });
    });
    const ser = Object.entries(series).map(([pf, vals]) => ({
        name: pf, type: "bar", stack: "total",
        emphasis: { focus: "series" },
        itemStyle: { color: PLATFORM_COLOR[pf] || "#888" },
        data: labels.map((l) => vals[l] || 0),
    }));
    distChart.setOption({
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        legend: { textStyle: { color: "#94a3b8" }, top: 0 },
        grid: { left: 50, right: 20, top: 40, bottom: 40 },
        xAxis: { type: "category", data: labels,
                 axisLabel: { color: "#94a3b8", fontSize: 11 },
                 axisLine: { lineStyle: { color: "#334155" } } },
        yAxis: { type: "value", axisLabel: { color: "#94a3b8" },
                 splitLine: { lineStyle: { color: "#334155" } } },
        series: ser,
    }, true);
}

function renderBox(trend) {
    if (!trend || !trend.length) { boxChart.clear(); return; }
    boxChart.setOption({
        tooltip: { trigger: "item" },
        legend: { textStyle: { color: "#94a3b8" } },
        grid: { left: 80, right: 20, top: 40, bottom: 30 },
        xAxis: { type: "category", data: trend.map((t) => t.platform),
                 axisLabel: { color: "#94a3b8" },
                 axisLine: { lineStyle: { color: "#334155" } } },
        yAxis: { type: "value", name: "价格 ¥", nameTextStyle: { color: "#94a3b8" },
                 axisLabel: { color: "#94a3b8" },
                 splitLine: { lineStyle: { color: "#334155" } } },
        series: [{
            name: "价格箱线", type: "boxplot",
            data: trend.map((t) => [t.min, t.q1, t.median, t.q3, t.max]),
            itemStyle: { color: "rgba(56,189,248,.25)", borderColor: "#38bdf8" },
        }, {
            name: "样本数", type: "scatter", symbolSize: 0,
            data: trend.map((t, i) => [i, t.max]),
            label: { show: true, formatter: (p) => "n=" + trend[p.dataIndex].count,
                     color: "#94a3b8", position: "top" },
        }],
    }, true);
}

function renderPicks(picks) {
    if (!picks || !picks.length) {
        $("picks").innerHTML = '<div class="stat">暂无推荐</div>';
        return;
    }
    $("picks").innerHTML = picks.map((p) => `
        <div class="pick ${p.rank === 1 ? "r1" : ""}">
            <span class="rank">#${p.rank}</span>
            <div class="title">${escapeHtml(p.title)}</div>
            <div class="price">¥${p.price.toFixed(2)}
                <span class="badge">${p.badge || ""}</span></div>
            <div class="meta">
                <span style="color:${PLATFORM_COLOR[p.platform] || "#fff"}">${p.platform}</span>
                <span>月销 ${fmtSales(p.sales)}</span>
                <span>评分 ${p.shop_rating}</span>
                <span>得分 ${p.value_score}</span>
            </div>
        </div>`).join("");
}

function renderPlatformStats(stats) {
    if (!stats || !stats.length) { $("platformStats").innerHTML = "暂无数据"; return; }
    $("platformStats").innerHTML = `
    <table>
        <tr>
            <th>平台</th><th>样本</th><th>最低(¥)</th><th>最高(¥)</th>
            <th>均价(¥)</th><th>中位(¥)</th><th>爆款</th>
        </tr>
        ${stats.map((s) => `
        <tr>
            <td style="color:${PLATFORM_COLOR[s.platform] || "#fff"}">${s.platform}</td>
            <td>${s.count}</td>
            <td class="price">${s.min_price.toFixed(2)}</td>
            <td>${s.max_price.toFixed(2)}</td>
            <td>${s.avg_price.toFixed(2)}</td>
            <td>${s.median_price.toFixed(2)}</td>
            <td>${s.best_seller ? `${fmtSales(s.best_seller.sales)} / ¥${s.best_seller.price.toFixed(0)}` : "-"}</td>
        </tr>`).join("")}
    </table>`;
}

function renderFilterBar(payload) {
    const platforms = [...new Set(payload.products.map((p) => p.platform))];
    const tags = ["全部", ...platforms];
    $("filterBar").innerHTML = tags.map((t) =>
        `<span class="tag-filter ${t === currentFilter ? "active" : ""}" data-pf="${t}">${t}</span>`
    ).join("");
    $("filterBar").querySelectorAll(".tag-filter").forEach((el) => {
        el.addEventListener("click", () => {
            currentFilter = el.dataset.pf;
            renderFilterBar(payload);
            renderTable(payload.products);
        });
    });
}

function renderTable(products) {
    const filtered = currentFilter === "all"
        ? products
        : products.filter((p) => p.platform === currentFilter);
    $("tableHint").textContent = `按价格升序 · 共 ${filtered.length} 条` +
        (currentFilter !== "all" ? ` · 仅 ${currentFilter}` : "");
    $("productTbody").innerHTML = filtered.map((p, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="pf-${pfKey(p.platform)}">${p.platform}</td>
            <td class="title" title="${escapeHtml(p.title)}">${escapeHtml(p.title)}</td>
            <td class="price">${p.price.toFixed(2)}</td>
            <td>${fmtSales(p.sales)}</td>
            <td>${escapeHtml(p.shop)}</td>
            <td>${p.shop_rating}</td>
            <td><span class="src-${p.source}">${p.source === "demo" ? "演示" : "真实"}</span></td>
            <td><a class="link" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">查看</a></td>
        </tr>`).join("");
}

function renderScrapers(scrapers) {
    if (!scrapers || !scrapers.length) { $("scrapers").innerHTML = "-"; return; }
    $("scrapers").innerHTML = scrapers.map((s) => `
        <div class="scraper-card">
            <b>${s.platform}</b>
            <span class="src-${s.source}">${s.source === "demo" ? "演示" : "真实"}</span>
            · real=${s.real_count} demo=${s.demo_count} · ${s.elapsed_ms}ms
        </div>`).join("");
}

function bannerUpdate(payload) {
    const anyReal = (payload.scraper_stats || []).some((s) => s.source === "real");
    const banner = $("banner");
    if (anyReal) {
        banner.innerHTML = `<b>说明：</b>本次含真实抓取结果。注意真实抓取受平台风控影响，结果仅供参考。`;
    } else {
        banner.innerHTML = `<b>说明：</b>本次为<b>演示数据</b>。京东/淘宝/拼多多均有登录态与风控反爬，在受限环境下自动回退到演示数据以保证可运行。`;
    }
}

// ---- 辅助 ------------------------------------------------------------
function setLoading(loading, msg) {
    if (loading) {
        $("runBtn").disabled = true;
        document.body.style.cursor = "wait";
    } else {
        $("runBtn").disabled = false;
        document.body.style.cursor = "";
    }
}
function showError(msg) {
    const existing = document.querySelector(".error-box");
    if (existing) existing.remove();
    const box = document.createElement("div");
    box.className = "error-box";
    box.textContent = msg;
    document.querySelector("main.container").prepend(box);
    setTimeout(() => box.remove(), 8000);
}
function fmtSales(n) {
    n = Number(n) || 0;
    return n >= 10000 ? (n / 10000).toFixed(1) + "万" : String(n);
}
function shortTitle(t, n) { return t.length > n ? t.slice(0, n - 1) + "…" : t; }
function pfKey(name) {
    return Object.entries(PLATFORM_KEY).find(([, v]) => v === name)?.[0] || "";
}
function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
