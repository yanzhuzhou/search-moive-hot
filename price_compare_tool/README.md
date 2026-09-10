# 电商商品价格自动化采集与对比工具

一个可开箱即跑的命令行工具 + Web 演示页，支持从 **京东 / 淘宝 / 拼多多** 按关键词批量采集商品信息，自动清洗去重、按价格升序排序，提供横向对比、性价比推荐与价格趋势可视化。

> 数据说明：受三大平台反爬、登录态、签名限制，真实接口需配合 Cookie/SDK 签名/代理池使用。本工具采用**适配器模式 + 确定性模拟数据生成器**，生成结构上与真实平台字段完全一致的商品数据，保证"可直接运行"。把 `BaseAdapter.USE_MOCK=False` 并实现 `fetch_raw` 即可无缝切换到真实采集，核心清洗/对比/可视化代码无需任何改动。

## 整体架构设计

```
┌──────────────────────────────────────────────────────────────┐
│                      CLI / Web 演示页                        │
│   (price_compare/cli.py  |  web/app.py + templates)          │
└──────────────────────────┬───────────────────────────────────┘
                           │ 关键词 + 平台集合
                           ▼
                  ┌────────────────────┐
                  │   CompareEngine    │  编排：采集→清洗→对比→可视化
                  └────────┬───────────┘
        ┌──────────────────┼──────────────────────┐
        ▼                  ▼                      ▼
 ┌─────────────┐   ┌──────────────┐   ┌────────────────┐
 │  Adapters   │   │   Cleaner    │   │   Comparator   │
 │ (JD/TB/PDD) │   │ 归一/去重/排序 │   │ 性价比/趋势/标签 │
 └──────┬──────┘   └──────────────┘   └────────────────┘
        │  Product 列表              │
        │                            ▼
        │                    ┌──────────────┐
        │                    │ Visualizer   │  4 张 ECharts 图 + 可选 PNG
        │                    └──────────────┘
        ▼
 ┌─────────────────────────────────────────┐
 │ Product（统一数据模型，所有平台归一化到此） │
 └─────────────────────────────────────────┘
```

### 分层职责

| 层 | 模块 | 职责 |
|---|---|---|
| 数据模型 | `models.py` | 统一 `Product` / `Source` 实体 |
| 采集层 | `adapters/` | 每平台一个 Adapter，把原生字段归一为 `Product` |
| 清洗层 | `cleaner.py` | 字段归一、去营销前缀、跨平台去重、价格升序 |
| 对比层 | `comparator.py` | 性价比评分、价格趋势、推荐标签、横向摘要 |
| 可视化 | `visualizer.py` | ECharts 4 图 + 可选 matplotlib PNG |
| 编排 | `engine.py` | `CompareEngine.run()` 串联全流程 |
| 入口 | `cli.py` / `web/app.py` | CLI 与 Web 共用同一引擎 |

### 适配器模式（开闭原则）

新增平台只需三步，不改动核心：
1. 继承 `BaseAdapter`，实现 `normalize()` 把平台字段映射到 `Product`；
2. 实现 `fetch_raw()`（真实接口）或覆盖 `_make_one_mock()`（演示）；
3. 在 `adapters/registry.py` 注册名字。

## 数据获取核心逻辑

### 采集流程（`BaseAdapter.search`）

```
search(keyword, limit):
    raw_items = fetch_raw(keyword, limit)   # 真实接口 或 模拟生成器
    products = [normalize(raw, keyword) for raw in raw_items]
    return products[:limit]
```

### 三大平台字段映射

| 平台 | 原生字段 | 归一化字段 |
|---|---|---|
| 京东 | `warename` / `jdPrice` / `commentCount` / `shopName` / `shopScore` / `skuId` / `itemLink` | title / price / sales / shop_name / shop_score / sku_id / url |
| 淘宝 | `title` / `price` / `sale` / `nick` / `shopcard` / `item_id` / `item_url` | 同上 |
| 拼多多 | `goods_name` / `goods_price` / `cnt` / `mall_name` / `mall_score` / `goods_id` / `link_url` | 同上 |

每个适配器的 `_make_one_mock` 用 **MD5(关键词+平台)** 作为随机种子，保证同一关键词多次运行结果一致（可复现），且价格/销量分布贴近真实平台特征（拼多多价更低销量更大、京东价偏高评分更高）。

### 清洗去重规则（`cleaner.py`）

1. **过滤**：丢弃价格≤0、标题为空、sku_id 为空的条目；
2. **标题清洗**：去 `【...】/[...]/(...)` 营销前缀，压缩多余空白；
3. **字段归一**：价格 2 位小数、评分裁剪到 [0,5]、销量整数；
4. **去重**：
   - 平台内严格按 `sku_id` 去重；
   - 跨平台：标题相似键（去标点后）长度≥6 且（完全一致 **或** 互为子串）+ 价格差 < `max(2元, 低价×5%)` → 视为同款，保留价格更低者；
5. **排序**：按价格升序。

### 性价比评分公式（可解释，便于在 Web 上展示）

```
value_score = 50 × (1 - price_norm)      # 价格越低越高（50%）
            + 25 × sales_norm            # 销量越高越高（25%）
            + 15 × score_norm            # 评分越高越高（15%）
            + 10 × platform_bonus        # 平台补贴：京东5% / 淘宝3% / 拼多多2%
```
各 `*_norm` 为该维度在当前关键词集合内的 min-max 归一。

### 推荐标签（互斥，按优先级）

| 标签 | 条件 |
|---|---|
| 全网最低 | 价格 ≤ 最低价 ×1.02 |
| 性价比之选 | value_score ≥70 且评分 ≥4.5 |
| 销量冠军 | 销量 ≥ 全集最高 ×0.95 |
| 品质优选 | 评分 ≥ 全集最高 ×0.99 且 ≥4.9 |
| 暂不推荐 | value_score <40 或 评分 <4.0 |
| （空） | 其余 |

## 数据可视化方案

Web 与 CLI 报告均使用 **ECharts 5**（CDN，无需后端依赖）渲染 4 张图：

1. **价格分布柱状图**：按价格升序，柱色按平台区分，直观看到低价区与高价区；
2. **各平台价格区间对比**：箱型图 + 散点叠加，对比三大平台的价格分布与离散度；
3. **性价比评分排名**：横向条形图，颜色按分段（绿≥70 / 橙≥50 / 红<50）；
4. **销量 vs 价格气泡图**：气泡大小=店铺评分，颜色按平台，一眼看出"低价高销量高评分"的甜区。

CLI 还可选 `--png` 用 matplotlib 导出静态图（独立 PNG，便于落盘归档）。

## 快速开始

### 环境要求
- Python 3.9+，**零额外依赖**即可运行（Web 图表用 ECharts CDN）
- 可选：`pip install matplotlib`（CLI 的 `--png` 静态图导出）

### 命令行工具

```bash
# 基础用法：采集并对比，输出 HTML 报告 + 终端表格
python run_cli.py 蓝牙耳机

# 完整选项
python run_cli.py 机械键盘 --per-platform 8 --output my_report.html --json result.json

# 只采集京东和拼多多
python run_cli.py 保温杯 --platforms jd pdd

# 额外导出 PNG 图表（需 matplotlib）
python run_cli.py 蓝牙耳机 --png

# 模块方式
python -m price_compare 蓝牙耳机
```

### Web 演示页

```bash
python run_web.py              # 默认 8787 端口
python run_web.py 9000         # 指定端口
```

浏览器打开 `http://localhost:8787/`：
- **首屏**自动展示示例关键词"蓝牙耳机"的采集结果 + 数据示例对照（每平台原始字段 vs 归一化 Product）；
- 顶部输入框输入任意关键词 → "采集并对比"按钮现场运行采集脚本，实时刷新统计、图表与明细表；
- 提供示例关键词芯片一键体验。

## 项目结构

```
price_compare_tool/
├── price_compare/                 # 核心包
│   ├── __init__.py / __main__.py
│   ├── models.py                  # Product / Source
│   ├── engine.py                  # CompareEngine 编排
│   ├── cleaner.py                 # 清洗去重排序
│   ├── comparator.py             # 性价比/趋势/标签/摘要
│   ├── visualizer.py             # ECharts 4 图 + matplotlib PNG
│   ├── cli.py                     # CLI 入口
│   └── adapters/
│       ├── base.py                # BaseAdapter + 模拟生成器基类
│       ├── jd.py / taobao.py / pdd.py
│       └── registry.py            # 适配器注册表
├── web/
│   ├── app.py                     # stdlib http.server 后端
│   ├── templates/index.html       # 演示页
│   └── static/app.js              # 前端逻辑
├── tests/test_tool.py             # 单元测试
├── run_cli.py / run_web.py        # 启动脚本
├── requirements.txt               # 可选依赖说明
└── README.md                      # 本文档
```

## 接入真实数据

把对应适配器的 `USE_MOCK = False`，并实现 `fetch_raw`：

```python
# price_compare/adapters/jd.py
class JDAdapter(BaseAdapter):
    USE_MOCK = False  # 切换到真实采集

    def fetch_raw(self, keyword: str, limit: int):
        # 真实实现：requests.get('https://api.m.jd.com/...',
        #   params={...}, headers={...}, cookies=..., timeout=10)
        # 反序列化为 dict 列表后返回
        ...
```

`normalize()` 无需改动——它只认字段名，不关心数据来源。后续的清洗、对比、可视化全部自动生效。
