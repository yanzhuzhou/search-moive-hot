# 国内电影票房数据分析看板

三源票房爬虫 + **四源评分/简介富集** + 多维度分析静态站点，对应网页链接：https://yanzhuzhou.github.io/search-moive-hot/。

## 核心功能

### 票房数据（三源融合）

| 数据集 | 口径 | 来源 |
|---|---|---|
| 🎬 **在映前十票房**（实时） | 当日 + 累计 + 占比 + 人次/场次 + 城市/院线/影院分布 + 七日趋势 | 中影票房网官方接口为主、猫眼专业版实时占比为辅 |
| 🏆 **年度前十票房（近似）** | 取在映影片**累计总票房**排序前十（非严格年度口径，页面已标注） | 中影票房网 `filmTotalSales` |

### 🌟 多平台评分与简介（四源富集）

点击榜单中的任意影片，即可查看其 **豆瓣 · 猫眼 · 淘票票 · TMDB** 四平台评分对比与影片简介。

| 平台 | 获取内容 | 接口 | 是否需要凭据 |
|---|---|---|---|
| **猫眼** m.maoyan.com | 购票评分 (`sc`) + 简介 (`dra`) | mmdb/movie/v5/{id}.json | ❌ 不需要 |
| **豆瓣** movie.douban.com | 评分 (`rating.value`) + 投票数 + 简介 | subject_suggest → rexxar JSON API | 可选（`DOUBAN_COOKIE` 提升成功率） |
| **TMDB** api.themoviedb.org | 评分 (`vote_average`) + 投票数 + 概述 (`overview`) | v3 search/movie + movie/detail | ✅ 需要 `TMDB_KEY` 或 `TMDB_TOKEN` |
| **淘票票** taopiaopiao.com | 评分 | 淘宝 mtop 签名搜索接口 | ✅ 需要 `TAOPIAOPIAO_COOKIE`（含 `__m_h5_tk`） |

> ⚠️ **豆瓣** 对云 IP / 数据中心 IP 有反爬限流机制，覆盖率取决于运行环境网络。代码采用**逐源缓存 + 失败自动重试**策略：成功的评分持久化到 `data/ratings_cache.json`，失败的源在下次运行时自动重试，确保最终完整性。
> ⚠️ **淘票票** 采用 mtop 签名方式，依赖淘宝开放平台签名算法，为尽力而为实现；若 API 变更可能失效，建议优先使用猫眼 + 豆瓣评分。

还支持 **🔍 影片检索与对比**：输入片名查看完整档案（海报 / 类型 / 上映日 / 多平台评分 / 简介 / 累计·当日票房 / 占比 / 人次），并与在映前十做累计+当日双维度对比。

---

## 快速开始（本地）

```bash
# 1. 安装依赖
pip install -r scripts/requirements.txt

# 2. 抓取数据（生成 data/，含 data/data.js 与影片丰富信息）
python scripts/crawler.py

# 3. 构建自包含页面（把 CSS + ECharts + 数据 + 逻辑内联进 index.html）
python scripts/build_index.py

# 4. 打开页面（二选一）
#    方式A：直接双击 index.html 即可（数据已内联为 window.BOXDATA，无需服务器）
#    方式B：本地起服务预览
python -m http.server 8000
#    浏览器访问 http://localhost:8000
```

> **为什么需要 build_index.py？** 为保证「双击 `index.html` 就能打开」（解决相对路径/外链加载失败导致的白屏），
> 构建脚本把 `assets/style.css`、`assets/echarts.min.js`、`data/data.js`、`assets/app.js` 全部内联进单一 `index.html`。
> 日常改完爬虫后跑一次 `build_index.py` 即可。

---

## 发布到 GitHub Pages

1. 将本仓库推送到 GitHub。
2. 仓库 **Settings → Pages → Build and deployment → Source 选 "Deploy from a branch"**，Branch 选 `main`、目录选 `/ (root)`。
3. 工作流 `.github/workflows/daily.yml` 会**每日自动抓取**并提交 `data/` 与 `index.html`，页面读取最新数据自动更新。
   - 也可在 Actions 页面手动 **Run workflow** 立即更新。
4. 访问 `https://<你的用户名>.github.io/<仓库名>/`。

---

## 环境变量与凭据

| 变量 | 用途 | 必需 | 获取方式 |
|---|---|---|---|
| `MY_COOKIE` | 猫眼专业版登录态（省份/受众画像） | ❌ 可选 | [猫眼专业版](https://piaofang.maoyan.com) → F12 Network → 复制 Cookie |
| `DOUBAN_COOKIE` | 豆瓣 Cookie（提升评分抓取成功率） | ❌ 可选 | 登录 [豆瓣](https://movie.douban.com) → F12 → 复制 Cookie |
| `TMDB_KEY` | TMDB v3 API Key（评分+简介） | ✅ 启用 TMDB 时需 | 注册 [TMDB](https://www.themoviedb.org/settings/api) 免费获取 |
| `TMDB_TOKEN` | TMDB v4 Bearer Token（替代 TMDB_KEY） | ✅ 二选一 | 同上，Settings → API → Create Access Token |
| `TAOPIAOPIAO_COOKIE` | 淘票票/淘宝 Cookie（含 `__m_h5_tk`） | ✅ 启用淘票票时需 | 登录 [淘票票](https://www.taopiaopiao.com) → F12 → 复制 Cookie |
| `TAOPIAOPIAO_APPSECRET` | 淘票票 mtop appSecret（覆盖默认值） | ❌ 可选 | 高级用户可自定义 |

**本地使用示例：**
```bash
TMDB_KEY="你的tmdb_key" python scripts/crawler.py
```

**GitHub Actions 配置：**
仓库 **Settings → Secrets and variables → Actions → New repository secret**，逐个添加上述变量名和值。工作流自动读取。

---

## 如何提供猫眼专业版 Cookie（解锁省份 / 受众画像）

省份明细、年龄/性别受众画像属于猫眼专业版**登录态数据**。获取与存放方式：

**步骤 1 — 取 Cookie**
1. 浏览器登录 [猫眼专业版](https://piaofang.maoyan.com)。
2. 按 `F12` → **Network（网络）** → 刷新页面 → 点任意请求 → **Request Headers** → 复制 `Cookie:` 整行的值。

**步骤 2 — 安全存放（切勿贴到聊天或提交到代码）**
- **本地测试**：放到 `config/cookie.txt`（已在 `.gitignore`，不会进仓库），或临时用环境变量：
  ```bash
  MY_COOKIE="你的cookie内容" python scripts/crawler.py
  ```
- **GitHub Pages 部署**：仓库 **Settings → Secrets and variables → Actions → New repository secret**，
  `Name=MY_COOKIE`，`Value=粘贴 Cookie`。工作流读取它自动跑，页面自动更新。

> ⚠️ Cookie 是你的**登录会话凭证，会过期**（通常几天到几周）。省份/画像失效时重新登录、更新 Secret 即可。
> 未配置 `MY_COOKIE` 时，省份/受众维度暂不展示，其余功能不受影响。

---

## 影片丰富（maoyan.ahua.space，默认开启）

爬虫按片名匹配猫眼 `movieId` 后，调用 [maoyan.ahua.space](https://maoyan.ahua.space) 的
`/api/movie/{id}`（Cloudflare Workers，支持 CORS）补全**海报 / 类型 / 上映日 / 剧情简介**，
写入 `data/movies.json` 并在检索卡片中展示。

> 该接口**只提供影片元数据、不含票房**（常返回「未找到票房数据」），票房仍以中影网/猫眼为准，仅用于丰富详情卡。

---

## 数据说明与局限

| 项 | 说明 |
|---|---|
| **票房数据源** | 中影票房网 `zgdypw.cn`（国家电影专资办官方）+ 猫眼专业版 `piaofang.maoyan.com` + apizero.cn（猫眼数据封装） |
| **评分/简介源** | 猫眼 m.maoyan.com（购票评分+简介）· 豆瓣 rexxar JSON（评分+简介）· TMDB（需密钥）· 淘票票（需Cookie，尽力而为） |
| **在映当日票房** | 采用 apizero 明文 `box_office`（万元），避免猫眼字体加密 |
| **累计票房** | apizero `total_box` + 猫眼 `sumBoxDesc`（明文）+ 中影网 `filmTotalSales`，统一换算为元展示 |
| **年度前十（近似）** | 「在映累计近似」口径：取在映影片累计总票房排序前十；含跨年影片历史累计，**非严格年度口径**，页面已明确标注 |
| **城市/院线/影院分布** | 中影网官方 `top10Citys / top10CinemaChains / top10Cinemas`（免费，替代拿不到的省份维度） |
| **七日趋势** | 中影网 `searchSevenDaysBoxOffice.json` |
| **省份 / 受众画像** | 需猫眼专业版登录态 Cookie（`MY_COOKIE`） |
| **实时大盘** | 中影网 `realtimedata.json`（当日总票房/人次/场次/营业影院数） |
| **评分缓存** | `data/ratings_cache.json` 逐源持久化；失败的源下次运行自动重试 |

---

## 目录结构

```
index.html               自包含单页应用（构建产物，双击即用）
assets/style.css         样式（SaaS 浅色主题）
assets/app.js            数据渲染 / 图表 / 检索对比 / 点击详情 / 评分展示
assets/echarts.min.js    本地 ECharts（内联用，避免 CDN 失败）
scripts/crawler.py        三源爬虫 + 四源评分/简介富集（豆瓣/猫眼/TMDB/淘票票）
scripts/build_index.py    把资源内联进 index.html 的构建脚本
scripts/requirements.txt
data/data.js             window.BOXDATA 全局变量（前端优先读取，支持 file://）
data/aggregate.json      完整结构化数据（含 ratings / intro 字段）
data/movies.json         影片主表（海报/类型/简介，按 movieId 缓存）
data/ratings_cache.json  评分缓存（按 movieId 或片名，逐源持久化）
data/history/            每日原始快照（透明可核查）
config/                  本地 Cookie 存放目录（gitignore）
.github/workflows/daily.yml  每日定时更新
```

## 免责声明

本项目仅用于数据分析学习，数据来自公开接口，不构成任何投资或商业建议。请遵守相关数据平台的使用条款。
