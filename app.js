/* 国内电影票房三源融合看板 — 前端逻辑（自包含，优先读取 window.BOXDATA）
   新增：点击影片查看 豆瓣/猫眼/淘票票/TMDB 评分对比 + 影片简介 */
(function () {
  "use strict";
  var DATA = window.BOXDATA || null;
  var charts = {};

  function el(id) { return document.getElementById(id); }
  function dispose(id) {
    if (charts[id]) { charts[id].dispose(); delete charts[id]; }
  }
  function initChart(id) {
    dispose(id);
    var dom = el(id);
    if (!dom) return null;
    var c = echarts.init(dom);
    charts[id] = c;
    return c;
  }

  /* 评分源元信息 */
  var SRC_META = {
    douban:      { label: "豆瓣",   color: "#2e9b57" },
    maoyan:      { label: "猫眼",   color: "#ff5a36" },
    taopiaopiao: { label: "淘票票", color: "#ff7a00" },
    tmdb:        { label: "TMDB",  color: "#01b4e4" },
  };
  var SRC_ORDER = ["douban", "maoyan", "taopiaopiao", "tmdb"];

  /* 格式化 */
  function fmtYuan(y) {
    if (y == null) return "—";
    y = Number(y);
    if (y >= 1e8) return (y / 1e8).toFixed(2) + "亿";
    if (y >= 1e4) return (y / 1e4).toFixed(1) + "万";
    return String(Math.round(y));
  }
  function fmtWan(w) {
    if (w == null) return "—";
    return Number(w).toFixed(2) + "万";
  }
  function fmtInt(n) {
    if (n == null) return "—";
    return Number(n).toLocaleString("zh-CN");
  }
  function fmtPct(v) {
    if (v == null) return "—";
    return Number(v).toFixed(1) + "%";
  }
  function fmtVotes(n) {
    if (n == null) return "";
    n = Number(n);
    if (n >= 1e4) return (n / 1e4).toFixed(1) + "万人评价";
    return n + "人评价";
  }
  function fmtScore(v) {
    if (v == null) return "—";
    return Number(v).toFixed(1);
  }

  /* 票房取值 */
  function cumBox(f) {
    return f.totalBoxYuan || f.mySumBoxYuan || f.zgFilmTotalSales || f.cumYuan || 0;
  }
  function dayBox(f) {
    if (f.daySalesYuan && f._source !== "zgdypw") return f.daySalesYuan;
    if (f.daySalesWan) return Math.round(f.daySalesWan * 10000);
    return f.daySalesYuan || 0;
  }
  function cumDesc(f) {
    return f.totalBoxDesc || f.mySumBoxDesc || fmtYuan(cumBox(f));
  }

  var BRAND = "#3563e9", ACCENT = "#ff7a45", PURPLE = "#7c4dff", GREEN = "#10b981";
  var PALETTE = ["#3563e9", "#7c4dff", "#ff7a45", "#10b981", "#f59e0b",
                 "#ef4444", "#06b6d4", "#8b5cf6", "#ec4899", "#22c55e"];

  /* ---------- 元信息 & 大盘条 ---------- */
  function renderMeta() {
    if (!DATA) { el("meta").textContent = "数据加载失败"; return; }
    var m = DATA.meta;
    el("meta").textContent = "数据日期 " + m.date +
      " · 更新 " + m.updated_at +
      (m.has_login_data ? " 🔐 含登录态数据" : "");
    el("disclaimer").textContent = "⚠️ " + (m.note || "");
  }

  function renderRealtime() {
    var rt = DATA.realtime, dt = DATA.day_total;
    var box = (rt && rt.box) || (dt && dt.box);
    var aud = (rt && rt.audience) || (dt && dt.audience);
    var ses = (rt && rt.session) || (dt && dt.session);
    var cine = dt && dt.cinemaCount;
    el("realtimeBar").innerHTML =
      item(fmtYuan(box), "当日大盘") +
      item(fmtInt(aud) + " 人", "观影人次") +
      item(fmtInt(ses) + " 场", "放映场次") +
      (cine ? item(fmtInt(cine) + " 家", "营业影院") : "");
  }
  function item(v, l) {
    return '<div class="item"><div class="v">' + v + '</div><div class="l">' + l + '</div></div>';
  }

  /* ---------- 在映前十 ---------- */
  function renderShowing() {
    var list = (DATA.showing.list || []).slice().sort(function (a, b) {
      return dayBox(b) - dayBox(a);
    });

    var c = initChart("showBar");
    if (c) {
      var names = list.map(function (x) { return x.name; }).reverse();
      var vals = list.map(function (x) { return dayBox(x); }).reverse();
      c.setOption({
        title: { text: "在映影片当日票房 TOP10（三源融合）", left: "center", textStyle: { fontSize: 15 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
          formatter: function (p) {
            var d = list[list.length - 1 - p[0].dataIndex];
            return d.name + "<br/>当日：" + fmtWan(d.daySalesWan) +
                   "<br/>累计：" + cumDesc(d) + "<br/>占比：" + fmtPct(d.boxRate);
          } },
        grid: { left: 10, right: 30, top: 56, bottom: 16, containLabel: true },
        xAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
        yAxis: { type: "category", data: names },
        series: [{ type: "bar", data: vals, barWidth: "58%",
          itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
            [{ offset: 0, color: BRAND }, { offset: 1, color: PURPLE }]), borderRadius: [0, 6, 6, 0] },
          label: { show: true, position: "right", formatter: function (p) { return fmtWan(p.value / 10000); } } }]
      });
      c.on("click", function (p) {
        var f = byName(p.name);
        if (f) showDetail(f);
      });
    }

    var rows = list.slice(0, 15).map(function (x) {
      return "<tr data-name=\"" + x.name + "\">" +
        '<td><span class="rank-badge ' + (x.rank <= 3 ? "top" : "") + '">' + x.rank + "</span></td>" +
        "<td><strong>" + x.name + "</strong></td>" +
        "<td>" + fmtWan(x.daySalesWan) + "</td>" +
        "<td>" + cumDesc(x) + "</td>" +
        "<td>" + fmtPct(x.boxRate) + "</td>" +
        "<td>" + fmtPct(x.showRate) + "</td>" +
        "<td>" + fmtPct(x.seatRate) + "</td>" +
        "<td>" + fmtInt(x.dayAudience) + "</td>" +
        "<td>" + (x.releaseDays || "—") + "</td></tr>";
    }).join("");
    el("showTable").querySelector("tbody").innerHTML = rows;
    wireRowClicks("showTable");

    renderDist("cityChart", "城市票房 TOP10", DATA.distribution.cities);
    renderDist("chainChart", "院线票房 TOP10", DATA.distribution.chains);
    renderDist("cinemaChart", "影院票房 TOP10", DATA.distribution.cinemas);
  }

  function renderDist(id, title, items) {
    var c = initChart(id);
    if (!c || !items || !items.length) return;
    var names = items.map(function (x) { return x.name; }).reverse();
    var vals = items.map(function (x) { return x.salesYuan || 0; }).reverse();
    c.setOption({
      title: { show: false },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
        formatter: function (p) { return p[0].name + "<br/>当日票房：" + fmtYuan(p[0].value) + " 元"; } },
      grid: { left: 10, right: 50, top: 12, bottom: 16, containLabel: true },
      xAxis: { type: "value", axisLabel: { fontSize: 11, formatter: function (v) { return fmtYuan(v); } } },
      yAxis: { type: "category", data: names, axisLabel: { fontSize: 12 } },
      series: [{ type: "bar", data: vals, barWidth: "55%",
        itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
          [{ offset: 0, color: GREEN }, { offset: 1, color: "#06b6d4" }]), borderRadius: [0, 5, 5, 0] },
        label: { show: true, position: "right", fontSize: 11, formatter: function (p) { return fmtYuan(p.value); } } }]
    });
  }

  /* ---------- 年度前十（近似） ---------- */
  function renderYearly() {
    var y = DATA.yearly;
    el("yearlyNote").textContent = "📌 " + (y.note || "") + "（数据日期 " + DATA.meta.date + "）";
    var list = (y.list || []).slice().sort(function (a, b) { return cumBox(b) - cumBox(a); });
    var c = initChart("yearBar");
    if (c) {
      var names = list.map(function (x) { return x.name; }).reverse();
      var vals = list.map(function (x) { return cumBox(x); }).reverse();
      c.setOption({
        title: { text: DATA.meta.year + " 年度累计票房 TOP10（在映近似）", left: "center", textStyle: { fontSize: 15 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
          formatter: function (p) { return p[0].name + "<br/>累计总票房：" + cumDesc(list[list.length - 1 - p[0].dataIndex]); } },
        grid: { left: 10, right: 30, top: 56, bottom: 16, containLabel: true },
        xAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
        yAxis: { type: "category", data: names },
        series: [{ type: "bar", data: vals, barWidth: "58%",
          itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
            [{ offset: 0, color: ACCENT }, { offset: 1, color: "#f59e0b" }]), borderRadius: [0, 6, 6, 0] },
          label: { show: true, position: "right", formatter: function (p) { return fmtYuan(p.value); } } }]
      });
      c.on("click", function (p) {
        var f = byName(p.name);
        if (f) showDetail(f);
      });
    }
    var rows = list.map(function (x) {
      return "<tr data-name=\"" + x.name + "\">" +
        '<td><span class="rank-badge ' + (x.rank <= 3 ? "top" : "") + '">' + x.rank + "</span></td>" +
        "<td><strong>" + x.name + "</strong></td>" +
        "<td>" + cumDesc(x) + "</td>" +
        "<td>" + fmtWan(x.daySalesWan) + "</td>" +
        "<td>" + (x.releaseDays || "—") + "</td>" +
        "</tr>";
    }).join("");
    el("yearTable").querySelector("tbody").innerHTML = rows;
    wireRowClicks("yearTable");
  }

  /* ---------- 市场洞察 ---------- */
  function renderInsight() {
    var t = DATA.trend7 || [];
    var c0 = initChart("weeklyChart");
    if (c0 && t.length) {
      var boxes = t.map(function (x) { return x.boxYuan; });
      var dates = t.map(function (x) { return String(x.date).slice(5); });
      var last = boxes[boxes.length - 1], prev = boxes[boxes.length - 2];
      var chg = (prev != null && prev) ? ((last - prev) / prev * 100) : null;
      el("weeklyNote").textContent = "口径：中影网官方近七日大盘。最新一日 " + t[t.length - 1].date +
        (chg != null ? ("，较前一日 " + (chg >= 0 ? "↑" : "↓") + " " + Math.abs(chg).toFixed(1) + "%") : "");
      c0.setOption({
        title: { text: "近 7 日大盘票房（元）", left: "center", textStyle: { fontSize: 15 } },
        tooltip: { trigger: "axis", formatter: function (p) {
          return p[0].name + "<br/>大盘：" + fmtYuan(p[0].value) + " 元"; } },
        grid: { left: 10, right: 20, top: 56, bottom: 16, containLabel: true },
        xAxis: { type: "category", data: dates },
        yAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
        series: [{ type: "line", smooth: true, data: boxes,
          symbolSize: 8, lineStyle: { width: 3, color: ACCENT }, itemStyle: { color: ACCENT },
          areaStyle: { color: new echarts.graphic.LinearGradient( 0, 0, 0, 1,
            [{ offset: 0, color: "rgba(255,122,69,.35)" }, { offset: 1, color: "rgba(255,122,69,0)" }]) },
          label: { show: true, formatter: function (p) { return fmtYuan(p.value); }, fontSize: 10 } }]
      });

      /* 排片-上座-票房 气泡图 */
      var c1 = initChart("scatterChart");
      if (c1) {
        var pts = (DATA.showing.list || []).filter(function (x) {
          return x.showRate != null && x.seatRate != null && dayBox(x) > 0;
        }).map(function (x) {
          return { name: x.name, value: [Number(x.showRate), Number(x.seatRate), dayBox(x)] };
        });
        var maxd = Math.max.apply(null, pts.map(function (p) { return p.value[ 2 ]; }));
        c1.setOption({
          tooltip: { formatter: function (p) {
            var v = p.value;
            return p.data.name + "<br/>排片率：" + v[0] + "%<br/>上座率：" + v[1] +
              "%<br/>当日票房：" + fmtWan(v[2] / 10000); } },
          grid: { left: 10, right: 18, top: 40, bottom: 40, containLabel: true },
          xAxis: { type: "value", name: "排片率(%)", nameLocation: "middle", nameGap: 25,
            axisLabel: { formatter: "{value}%" } },
          yAxis: { type: "value", name: "上座率(%)", nameLocation: "middle", nameGap: 28,
            axisLabel: { formatter: "{value}%" } },
          series: [{ type: "scatter", data: pts,
            symbolSize: function (v) { return 14 + (maxd ? v[2] / maxd * 34 : 14); },
            itemStyle: { color: "rgba(53,99,233,.78)", borderColor: BRAND, borderWidth: 1 },
            label: { show: true, formatter: function (p) { return p.data.name; }, position: "top", fontSize: 10 } }]
        });
      }

      /* 类型分布 */
      var c3 = initChart("genreChart");
      if (c3) {
        var gmap = {};
        (DATA.showing.list || []).forEach(function (x) {
          var cats = String(x.category || "").split(",").map(function (s) { return s.trim(); }).filter(Boolean);
          var v = dayBox(x);
          cats.forEach(function (c) { gmap[c] = (gmap[c] || 0) + v; });
        });
        var arr = Object.keys(gmap).map(function (k) { return { name: k, value: gmap[k] }; })
          .sort(function (a, b) { return a.value - b.value; }).reverse().slice(0, 12);
        c3.setOption({
          title: { text: "各类型当日票房累计（元）", left: "center", textStyle: { fontSize: 14 } },
          tooltip: { trigger: "axis", formatter: function (p) { return p[0].name + "：" + fmtYuan(p[0].value); } },
          grid: { left: 10, right: 55, top: 48, bottom: 10, containLabel: true },
          xAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
          yAxis: { type: "category", data: arr.map(function (x) { return x.name; }), axisLabel: { fontSize: 13 } },
          series: [{ type: "bar", data: arr.map(function (x) { return x.value; }), barWidth: "62%",
            itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 1, 0,
              [{ offset: 0, color: PURPLE }, { offset: 1, color: ACCENT }]), borderRadius: [0, 5, 5, 0] },
            label: { show: true, position: "right", fontSize: 11, formatter: function (p) { return fmtYuan(p.value); } } }]
        });
      }
    }
  }

  /* ---------- 影片查找 ---------- */
  function byName(name) {
    var all = (DATA.showing.list || []).concat(DATA.yearly.list || []);
    for (var i = 0; i < all.length; i++) {
      if (all[i].name === name) return all[i];
    }
    return null;
  }
  function findFilm(q) {
    q = (q || "").trim();
    if (!q) return null;
    var hit = byName(q);
    if (hit) return hit;
    var all = (DATA.showing.list || []).concat(DATA.yearly.list || []);
    hit = all.find(function (x) { return x.name && x.name.indexOf(q) >= 0; });
    if (hit) return hit;
    var mk = DATA.movies || {};
    for (var k in mk) {
      if (mk[k].name && (mk[k].name === q || mk[k].name.indexOf(q) >= 0)) {
        return { name: mk[k].name, movieId: k, poster: mk[k].poster,
          category: mk[k].category, releaseDate: mk[k].releaseDate, summary: mk[k].summary, _onlyMeta: true };
      }
    }
    return null;
  }

  /* ---------- 评分徽章 HTML ---------- */
  function ratingBadges(f) {
    var ratings = f.ratings || {};
    var html = '<div class="ratings">';
    SRC_ORDER.forEach(function (src) {
      var meta = SRC_META[src];
      var r = ratings[src];
      if (r && r.score != null) {
        html += '<div class="rating-badge" style="--c:' + meta.color + '">' +
          '<span class="rb-src">' + meta.label + '</span>' +
          '<span class="rb-score">' + fmtScore(r.score) + '</span>' +
          (r.votes != null ? '<span class="rb-votes">' + fmtVotes(r.votes) + '</span>' : '') +
          (r.url ? '<a class="rb-link" href="' + r.url + '" target="_blank" rel="noopener" title="在' + meta.label + '查看">↗</a>' : '') +
          '</div>';
      } else {
        html += '<div class="rating-badge muted">' +
          '<span class="rb-src">' + meta.label + '</span>' +
          '<span class="rb-score">暂无</span></div>';
      }
    });
    html += '</div>';
    return html;
  }

  /* ---------- 评分对比图 ---------- */
  function renderRatingsChart(f) {
    var c = initChart("ratingsChart");
    if (!c) return;
    var ratings = f.ratings || {};
    var labels = [], vals = [], colors = [];
    SRC_ORDER.forEach(function (src) {
      var r = ratings[src];
      if (r && r.score != null) {
        labels.push(SRC_META[src].label);
        vals.push(Number(r.score));
        colors.push(SRC_META[src].color);
      }
    });
    if (!labels.length) { c.clear(); return; }
    var isSingle = labels.length <= 1;
    c.setOption({
      title: { text: "多平台评分对比（满分 10）", left: "center", textStyle: { fontSize: 14 } },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
        formatter: function (p) { return p[0].name + "：" + p[0].value + " 分"; } },
      grid: { left: 10, right: 50, top: 52, bottom: 16, containLabel: true },
      xAxis: { type: "value", max: 10, axisLabel: { formatter: "{value}" }, interval: 2 },
      yAxis: { type: "category", data: labels.reverse(), axisLabel: { fontSize: 13, fontWeight: 600 } },
      series: [{ type: "bar", data: vals.slice().reverse().map(function (v, i) {
          return { value: v, itemStyle: { color: colors.slice().reverse()[i], borderRadius: [0, 6, 6, 0] } };
        }), barWidth: isSingle ? "35%" : "55%",
        barMaxWidth: isSingle ? 120 : undefined,
        label: { show: true, position: "right", fontSize: 14, fontWeight: "bold",
          formatter: function (p) { return p.value + " 分"; } } }]
    });
  }

  /* ---------- 影片详情（点击 / 检索触发）---------- */
  function showDetail(f) {
    var card = el("movieProfile");
    var note = el("searchHint");
    var cmp = el("compareChart"), cmpTrend = el("compareTrendChart");
    var rc = el("ratingsChart");

    if (!f) {
      card.classList.add("hidden"); cmp.classList.add("hidden"); rc.classList.add("hidden");
      cmpTrend.classList.add("hidden");
      return;
    }
    if (note) note.classList.add("hidden");

    var showHit = (DATA.showing.list || []).find(function (x) { return x.name === f.name; });
    var yearHit = (DATA.yearly.list || []).find(function (x) { return x.name === f.name; });
    var rankTxt = showHit ? ("在映第 " + showHit.rank + " 名") :
                     (yearHit ? ("年度近似第 " + yearHit.rank + " 名") : "未进入榜单");

    var poster = f.poster ? '<img src="' + f.poster + '" alt="poster" onerror="this.style.display=\'none\'"/>' : "";
    var info =
      '<div class="profile-info">' +
        "<h3>🎬 " + f.name + "</h3>" +
        '<div class="line">类型：' + (f.category || "—") + "　|　上映：" + (f.releaseDate || "—") +
        (f.releaseDays ? "　|　" + f.releaseDays : "") + "</div>" +
        '<div class="line">排名：' + rankTxt +
        (f._source && !f._onlyMeta ? "　|　数据来源：" + f._source : "") + "</div>" +
        '<div class="kpis">' +
          kpi(cumDesc(f), "累计票房") +
          kpi(fmtWan(f.daySalesWan), "当日票房") +
          kpi(fmtPct(f.boxRate), "今日占比") +
          kpi(fmtPct(f.showRate), "排片占比") +
          kpi(fmtPct(f.seatRate), "上座率") +
          kpi(fmtInt(f.dayAudience), "当日人次") +
        "</div>" +
        ratingBadges(f) +
        (f.intro ? '<div class="intro"><b>影片简介</b>' +
            (f.intro_source ? ' <span class="src">来源：' + f.intro_source + "</span>" : "") +
            "<p>" + escapeHtml(f.intro) + "</p></div>" : "") +
      "</div>";
    card.innerHTML = poster + info;
    card.classList.remove("hidden");
    el("clickHint").classList.add("hidden");

    /* 评分对比图 */
    renderRatingsChart(f);
    rc.classList.remove("hidden");

    /* 累计对比 */
    var c = initChart("compareChart");
    if (c) {
      var top = (DATA.showing.list || []).slice().sort(function (a, b) { return dayBox(b) - dayBox(a); });
      var names = top.map(function (x) { return x.name; });
      var vals = top.map(function (x) { return cumBox(x); });
      var fIdx = names.indexOf(f.name);
      var fVal = fIdx >= 0 ? vals[fIdx] : cumBox(f);
      if (fIdx < 0) { names.unshift("★ " + f.name); vals.unshift(fVal); }
      else { names[fIdx] = "★ " + f.name; }
      c.setOption({
        title: { text: "累计票房对比（★ = 当前影片）", left: "center", textStyle: { fontSize: 14 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
          formatter: function (p) {
            var nm = p[0].name.replace("★ ", "");
            var fi = byName(nm) || {};
            return nm + "<br/>累计：" + cumDesc(fi) + "<br/>当日：" + fmtWan(fi.daySalesWan);
          } },
        grid: { left: 10, right: 55, top: 52, bottom: 16, containLabel: true },
        xAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
        yAxis: { type: "category", data: names.slice().reverse(), axisLabel: { fontSize: 11 } },
        series: [{ type: "bar", data: vals.slice().reverse(), barWidth: "52%",
          itemStyle: { color: function (p) {
            return p.name.indexOf("★") === 0 ? ACCENT : BRAND; }, borderRadius: [0, 5, 5, 0] },
          label: { show: true, position: "right", fontSize: 10, formatter: function (p) { return fmtYuan(p.value); } } }]
      });
      cmp.classList.remove("hidden");
    }

    /* 当日对比 */
    var c2 = initChart("compareDayChart");
    if (c2) {
      var top2 = (DATA.showing.list || []).slice().sort(function (a, b) { return dayBox(b) - dayBox(a); });
      var n2 = top2.map(function (x) { return x.name; });
      var v2 = top2.map(function (x) { return dayBox(x); });
      var fI2 = n2.indexOf(f.name);
      var fV2 = fI2 >= 0 ? v2[fI2] : dayBox(f);
      if (fI2 < 0) { n2.unshift("★ " + f.name); v2.unshift(fV2); }
      else { n2[fI2] = "★ " + f.name; }
      c2.setOption({
        title: { text: "当日票房对比（★ = 当前影片）", left: "center", textStyle: { fontSize: 14 } },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" },
          formatter: function (p) { return p[0].name.replace("★ ", "") + "<br/>当日：" + fmtWan(p[0].value / 10000); } },
        grid: { left: 10, right: 55, top: 52, bottom: 16, containLabel: true },
        xAxis: { type: "value", axisLabel: { formatter: function (v) { return fmtYuan(v); } } },
        yAxis: { type: "category", data: n2.slice().reverse(), axisLabel: { fontSize: 11 } },
        series: [{ type: "bar", data: v2.slice().reverse(), barWidth: "52%",
          itemStyle: { color: function (p) {
            return p.name.indexOf("★") === 0 ? PURPLE : GREEN; }, borderRadius: [0, 5, 5, 0] },
          label: { show: true, position: "right", fontSize: 10, formatter: function (p) { return fmtWan(p.value / 10000); } } }]
      });
      el("compareDayWrap").classList.remove("hidden");
    }

    cmpTrend.classList.add("hidden");

    /* 平滑滚动到详情区 + 延迟 resize 确保网格容器尺寸正确 */
    try { card.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e) {}
    requestAnimationFrame(function () {
      Object.keys(charts).forEach(function (k) { if (charts[k]) charts[k].resize(); });
    });
  }
  function kpi(v, l) { return '<div class="kpi"><div class="v">' + v + '</div><div class="l">' + l + "</div></div>"; }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function wireRowClicks(tableId) {
    var tbody = el(tableId).querySelector("tbody");
    if (!tbody) return;
    tbody.querySelectorAll("tr[data-name]").forEach(function (tr) {
      tr.addEventListener("click", function () {
        var f = byName(tr.getAttribute("data-name"));
        if (f) showDetail(f);
      });
    });
  }

  function doSearch() {
    var q = el("searchInput").value;
    var f = findFilm(q);
    if (!f) {
      el("movieProfile").classList.add("hidden");
      el("compareChart").classList.add("hidden");
      el("ratingsChart").classList.add("hidden");
      el("compareDayWrap").classList.add("hidden");
      var hint = el("searchHint");
      hint.textContent = "未找到影片「" + q + "」，请检查片名（可输入部分关键字）。";
      hint.classList.remove("hidden");
      return;
    }
    showDetail(f);
  }

  /* ---------- 初始化 ---------- */
  function init() {
    if (!DATA) { el("meta").textContent = "数据加载失败：请先运行爬虫生成 data/data.js"; return; }
    renderMeta();
    renderRealtime();

    var tabs = document.querySelectorAll(".tab");
    tabs.forEach(function (t) {
      t.addEventListener("click", function () {
        tabs.forEach(function (x) { x.classList.remove("active"); });
        t.classList.add("active");
        document.querySelectorAll(".view").forEach(function (v) { v.classList.remove("active"); });
        var v = el(t.dataset.view);
        if (v) v.classList.add("active");
        setTimeout(function () { Object.keys(charts).forEach(function (k) { charts[k].resize(); }); }, 30);
      });
    });

    el("searchBtn").addEventListener("click", doSearch);
    el("searchInput").addEventListener("keydown", function (e) { if (e.key === "Enter") doSearch(); });

    renderShowing();
    renderYearly();
    renderInsight();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else { init(); }
})();
