/* 演示页前端逻辑 */
'use strict';

let _echartsInst = []; // 保存图表实例以便 resize

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function fmtSales(n) {
  n = +n || 0;
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return n.toLocaleString();
}
function platClass(p) {
  return p === '京东' ? 'jd' : p === '淘宝' ? 'tb' : 'pdd';
}

function renderStats(summary) {
  const box = document.getElementById('statsBox');
  if (!summary || !summary.count) { box.innerHTML = ''; return; }
  const platStats = summary.platform_stats || [];
  const globalCards = [
    { label: '商品总数', value: summary.count, cls: 'accent' },
    { label: '全网最低价', value: '¥' + summary.global_min, cls: '' },
    { label: '全网最高价', value: '¥' + summary.global_max, cls: '' },
    { label: '均价', value: '¥' + summary.global_avg, cls: '' },
  ];
  let html = globalCards.map(c =>
    `<div class="stat-card"><div class="label">${c.label}</div><div class="value ${c.cls}">${c.value}</div></div>`
  ).join('');
  platStats.forEach(ps => {
    html += `<div class="stat-card">
      <div class="label">${esc(ps.platform)} · ${ps.count} 条</div>
      <div class="value ${platClass(ps.platform)}">¥${ps.min_price}~${ps.max_price}</div>
      <div style="font-size:11px;color:#6b7280;margin-top:4px">均价 ¥${ps.avg_price} · 均销 ${fmtSales(ps.avg_sales)} · 均评分 ${ps.avg_score}</div>
    </div>`;
  });
  box.innerHTML = html;
}

function renderTable(products) {
  const tb = document.getElementById('tbody');
  if (!products || !products.length) {
    tb.innerHTML = '<tr><td colspan="9" class="status">无匹配商品</td></tr>';
    return;
  }
  tb.innerHTML = products.map((p, i) => {
    const tag = p.recommend_tag ? `<span class="tag ${esc(p.recommend_tag)}">${esc(p.recommend_tag)}</span>` : '-';
    return `<tr>
      <td>${i + 1}</td>
      <td><span class="badge ${esc(p.platform)}">${esc(p.platform)}</span></td>
      <td class="price">¥${(+p.price).toFixed(2)}</td>
      <td>${fmtSales(p.sales)}</td>
      <td>${(+p.shop_score).toFixed(2)}</td>
      <td>${(+p.value_score).toFixed(1)}</td>
      <td>${tag}</td>
      <td>${esc(p.trend || '-')}</td>
      <td class="title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>
        <span class="shop">${esc(p.shop_name)}</span></td>
    </tr>`;
  }).join('');
}

function renderCharts(html) {
  const box = document.getElementById('chartBox');
  if (!html) {
    box.innerHTML = '<div class="chart-card"><div class="status">暂无图表数据</div></div>';
    return;
  }
  // 注入图表 HTML（含 <script>），通过临时容器执行
  _echartsInst.forEach(c => { try { c.dispose(); } catch (e) {} });
  _echartsInst = [];
  box.innerHTML = html;
  // HTML 中已含 ECharts 初始化脚本，浏览器会自动执行 innerHTML 里的 <script> 吗？
  // 不会自动执行。需要手动执行：
  const scripts = box.querySelectorAll('script');
  scripts.forEach(old => {
    const s = document.createElement('script');
    if (old.src) { s.src = old.src; s.onload = () => {}; }
    else { s.text = old.textContent; }
    old.parentNode.replaceChild(s, old);
  });
}

function showLoading(msg) {
  document.getElementById('chartBox').innerHTML =
    `<div class="chart-card" style="grid-column:1/-1"><div class="status"><span class="loading"></span>${esc(msg)}</div></div>`;
  document.getElementById('tbody').innerHTML =
    '<tr><td colspan="9" class="status"><span class="loading"></span>采集中...</td></tr>';
}

function showAlert(msg, isErr) {
  const box = document.getElementById('alertBox');
  box.innerHTML = msg ? `<div class="error">${esc(msg)}</div>` : '';
}

async function loadSample() {
  try {
    const r = await fetch('/api/sample');
    const data = await r.json();
    if (data.error) { showAlert(data.error); return; }
    renderResult(data, '（示例数据）');
    // 加载示例图表
    const cr = await fetch('/api/charts?kw=');
    const html = await cr.text();
    renderCharts(html);
  } catch (e) {
    showAlert('加载示例失败：' + e.message);
  }
}

function renderResult(data, suffix) {
  renderStats(data.summary);
  renderTable(data.products);
  document.getElementById('runBtn').disabled = false;
  document.getElementById('runBtn').textContent = '采集并对比';
}

async function runCompare() {
  const kw = document.getElementById('kw').value.trim();
  if (!kw) { showAlert('请输入关键词'); return; }
  showAlert('');
  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.textContent = '采集中...';
  showLoading('正在从京东/淘宝/拼多多采集“' + kw + '”...');
  try {
    const r = await fetch('/api/compare?kw=' + encodeURIComponent(kw));
    const data = await r.json();
    if (data.error) { showAlert(data.error); btn.disabled = false; btn.textContent = '采集并对比'; return; }
    renderResult(data);
    // 现场运行的图表
    const cr = await fetch('/api/charts?kw=' + encodeURIComponent(kw));
    const html = await cr.text();
    renderCharts(html);
  } catch (e) {
    showAlert('采集失败：' + e.message);
    btn.disabled = false;
    btn.textContent = '采集并对比';
  }
}

function renderDataExample(data) {
  const box = document.getElementById('dataExampleBox');
  if (!data || !data.pairs || !data.pairs.length) { box.innerHTML = ''; return; }
  const cards = data.pairs.map(pr => {
    const rawJson = JSON.stringify(pr.raw, null, 2);
    const normJson = pr.normalized ? JSON.stringify(pr.normalized, null, 2) : 'null';
    return `<div class="de-card">
      <div class="de-head"><span class="badge ${esc(pr.platform)}">${esc(pr.platform)}</span> 原始字段 → 归一化结果</div>
      <div style="display:flex; gap:0;">
        <div class="de-col" style="flex:1;">
          <div class="de-sub">原始字段（数据示例）</div>
          <pre>${esc(rawJson)}</pre>
        </div>
        <div class="de-col" style="flex:1;">
          <div class="de-sub">归一化 Product（结果示例）</div>
          <pre>${esc(normJson)}</pre>
        </div>
      </div>
    </div>`;
  }).join('');
  box.innerHTML = `<details open>
    <summary>📥 数据示例 & 结果示例 <span class="badge 京东">京东</span><span class="badge 淘宝">淘宝</span><span class="badge 拼多多">拼多多</span>
      <span style="font-weight:400;color:#6b7280;font-size:12px;margin-left:8px">采集到的原生字段 vs 适配器归一化后的统一字段</span></summary>
    <div style="font-size:12px;color:#6b7280;margin:8px 0">${esc(data.description)}</div>
    <div class="de-grid">${cards}</div>
  </details>`;
}

async function loadDataExample() {
  try {
    const r = await fetch('/api/data-example');
    const data = await r.json();
    renderDataExample(data);
  } catch (e) {
    document.getElementById('dataExampleBox').innerHTML = '';
  }
}

// 回车触发
document.getElementById('kw').addEventListener('keydown', e => {
  if (e.key === 'Enter') runCompare();
});

// 初始化：先加载示例 + 数据示例
window.addEventListener('DOMContentLoaded', () => {
  loadSample();
  loadDataExample();
});
