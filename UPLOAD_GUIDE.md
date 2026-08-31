# 上传到 GitHub 并开启「点开即用」网页 · 小白教程

本压缩包是一个**自包含**的票房看板：双击 `index.html` 就能在浏览器打开，无需任何服务器。
上传到 GitHub 后，开启 **GitHub Pages**，就能得到一个网址，任何人点开即可看。

---

## 一、准备工作

1. 注册并登录 [github.com](https://github.com)（免费）
2. 把 `movie-box-office-dashboard.zip` 解压到电脑任意文件夹
3. 解压后你会看到这些文件和文件夹（**注意：文件夹结构必须原样保留，不要拍平**）：

```
movie-box-office-dashboard/
├── index.html          ← 核心网页（自包含，双击即用）
├── assets/             ← 样式、脚本、图表库（必须保留文件夹）
├── scripts/            ← 爬虫与构建脚本
├── data/               ← 已抓取的票房数据
├── .github/            ← ⭐ 自动/手动更新数据的配置（关键，别漏）
│   └── workflows/
│       └── daily.yml   ← 每天自动跑 + 允许手动点击触发
├── .nojekyll           ← 让 GitHub 直接伺服静态网页（别删）
├── .gitignore
├── README.md
└── UPLOAD_GUIDE.md     ← 本教程
```

---

## 二、方法一：GitHub 网页直接上传（最简单，推荐）

1. 登录 github.com，点右上角 **`+`** → **New repository**
2. **Repository name** 填：`movie-box-office-dashboard`
3. 选 **Public**（公开，这样 Pages 免费且网址谁都能开）
4. **不要**勾选 "Add a README file"（我们已有）
5. 点 **Create repository**
6. 在出现的空仓库页，点蓝字 **"uploading an existing file"**
7. 把解压文件夹里的**全部内容**一起拖进上传框
   - ⚠️ **关键**：`assets`、`scripts`、`data`、`.github` 是**文件夹**，直接把整个文件夹拖进去
   - 不要只把里面的文件零散拖进去，那样会把 `daily.yml` 拍平到根目录，自动更新就失效了
   - `.github` 和 `.nojekyll` 是隐藏文件/文件夹，拖拽时一起选中拖入
8. 拉到页面底部，点绿色的 **Commit changes**
9. 上传后确认仓库里能看到 `assets/`、`scripts/`、`data/`、`.github/` 这几个**文件夹**（而不是零散文件），说明结构对了

---

## 三、开启 GitHub Pages（得到可点击的网址）

1. 进入你的仓库页，点上方 **Settings**
2. 左侧菜单点 **Pages**
3. **Build and deployment** → **Source** 选 **Deploy from a branch**
4. **Branch** 选 `main`（若你提交到的分支叫 master 就选 master）→ 右侧选 **/(root)** → **Save**
5. 页面顶部会提示：`Your site is published at https://你的用户名.github.io/movie-box-office-dashboard/`
6. 等待 **1–2 分钟**，打开这个网址即可看到看板（点开即用 ✅）

---

## 四、方法二：用 GitHub Desktop（隐藏文件多时最稳妥）

若网页上传时 `.github` / `.nojekyll` 等隐藏文件没传上去，或担心拍平目录，用桌面客户端最省心：

1. 下载安装 [GitHub Desktop](https://desktop.github.com/)
2. 登录你的账号
3. `File` → `Clone repository` 克隆你刚建的空仓库到本地
4. 把解压文件夹里的**所有内容**（含 `assets/`、`scripts/`、`data/`、`.github/` 等文件夹）复制进克隆下来的文件夹
5. 左上角填一个 Summary（如 `init`），点 **Commit to main**
6. 点 **Push origin** 推送到 GitHub
7. 回到网站，按「三、开启 GitHub Pages」步骤操作

---

## 五、⭐ 如何让数据更新（你最关心的）

**GitHub Pages 只是展示文件，它不会自己跑爬虫。** 数据更新靠仓库里的 `.github/workflows/daily.yml`（GitHub Actions 自动任务）。有两种方式：

### 方式 A：手动点一下立刻更新（无需任何配置）

1. 进入你的仓库页，点上方 **Actions**
2. 左侧列表点 **每日票房数据更新**
3. 右侧点 **Run workflow**（绿色按钮）→ 再点一次 **Run workflow**
4. 等约 1–2 分钟，任务跑完会自动把新数据提交到仓库
5. 刷新你的网页（`https://你的用户名.github.io/...`），数据就更新了

> 前提：`.github/workflows/daily.yml` 必须在正确位置（按本教程上传即满足）。
> 若 Actions 页提示 "Permission denied" 或无写入权限，见下方「权限设置」。

### 方式 B：每天自动更新（一次设置，永久省心）

`daily.yml` 已内置每天 00:00（北京时间）自动抓取的定时任务。只需确认仓库权限：

1. 进入仓库页 **Settings** → 左侧 **Actions** → **General**
2. 拉到 **Workflow permissions**，选 **Read and write permissions**
3. 点 **Save**
4. 之后每天凌晨会自动更新，网页次日打开就是新数据

### 权限设置（若手动触发报 "Permission denied"）

仓库 **Settings → Actions → General → Workflow permissions → Read and write permissions → Save**

---

## 六、常见问题

- **网页打不开 / 显示 404？**
  检查 Settings → Pages 里选的分支是否正确，且 `index.html` 在仓库**根目录**（不是子文件夹里）。
- **样式/图表错乱？**
  确认 `assets` 文件夹一起上传了，且 `index.html` 和 `assets` 在同一级。
- **`.nojekyll` 没传上去？**
  在仓库页点 **Add file** → **Create new file**，文件名填 `.nojekyll`，内容留空，提交即可。
- **数据不更新 / 手动点击没反应？**
  99% 是因为 `daily.yml` 被拍平到了根目录（不在 `.github/workflows/` 里）。按本教程重新上传、保持文件夹结构即可。
- **想解锁省份明细等更多数据？**（可选）
  仓库 Settings → **Secrets and variables** → Actions → 添加 `MY_COOKIE` 密钥（猫眼专业版 Cookie）。不加也能正常用，只是没有登录态专属数据。

---

完成！你现在拥有了一个可公开访问、且能一键/每天自动更新数据的票房看板网页。
