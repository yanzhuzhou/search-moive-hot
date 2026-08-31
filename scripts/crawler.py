#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
国内电影票房三源融合爬虫（含多平台评分/简介富集）
====================================================
票房数据源（同前）：
  1) apizero.cn（第三方封装，猫眼数据）— 在映 Top10 明文当日票房
  2) 中影票房网（国家电影专资办官方）zgdypw.cn — 城市/院线/影院分布 + 七日趋势
  3) 猫眼专业版 piaofang.maoyan.com — 累计票房 + 影片 ID 匹配

新增：影片评分 / 简介 四源富集
  - 猫眼   : m.maoyan.com/mmdb/movie/v5/{id}.json  -> 购票评分 sc + 简介 dra
  - 豆瓣   : movie.douban.com/j/subject_suggest（取 id）
             + m.douban.com/rexxar/api/v2/movie/{id}（JSON 评分 + 简介）
  - TMDB   : api.themoviedb.org/3  (需 TMDB_KEY / TMDB_TOKEN 环境变量)
  - 淘票票 : 淘宝 mtop 签名接口（需 TAOPIAOPIAO_COOKIE，尽力而为）

输出：
  data/data.js          -> window.BOXDATA（供自包含 index.html 直接读取）
  data/aggregate.json   -> 完整结构化数据
  data/movies.json      -> 影片主表（海报/类型/简介/评分缓存）
  data/ratings_cache.json -> 评分缓存（按 movieId 或 片名）
  data/history/<date>.json -> 每日原始快照
"""
import os, sys, json, time, re, datetime, hashlib

try:
    import requests
except ImportError:
    sys.exit("缺少依赖：请先 `pip install -r scripts/requirements.txt`")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")

# ---- 环境变量（可选凭据）----
MY_COOKIE = os.environ.get("MY_COOKIE", "").strip()          # 猫眼专业版登录态
DOUBAN_COOKIE = os.environ.get("DOUBAN_COOKIE", "").strip()  # 豆瓣（提升成功率，可选）
TMDB_KEY = os.environ.get("TMDB_KEY", "").strip()            # TMDB v3 api_key
TMDB_TOKEN = os.environ.get("TMDB_TOKEN", "").strip()        # TMDB v4 bearer token
TAO_COOKIE = os.environ.get("TAOPIAOPIAO_COOKIE", "").strip() # 淘票票/淘宝 Cookie（含 __m_h5_tk）
TAO_SECRET = os.environ.get("TAOPIAOPIAO_APPSECRET", "").strip()  # 淘票票 mtop appSecret（可选覆盖）

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HIST = os.path.join(DATA, "history")
os.makedirs(HIST, exist_ok=True)


def log(*a):
    print("[crawler]", *a, file=sys.stderr, flush=True)


def get(url, headers=None, timeout=20, params=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    return requests.get(url, headers=h, timeout=timeout, params=params)


# ---------- 工具 ----------
def parse_cn_amount(s):
    """解析 '16.35亿' / '1234万' -> 元(int)。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).strip()
    if not s:
        return None
    m = re.match(r"([\d.]+)\s*(亿|万)?", s)
    if not m:
        try:
            return int(float(s))
        except ValueError:
            return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "亿":
        return int(num * 1e8)
    if unit == "万":
        return int(num * 1e4)
    return int(num)


def wan_to_yuan(v):
    """中影网数值单位为万元，转元。"""
    if v is None:
        return None
    try:
        return int(float(v) * 1e4)
    except (ValueError, TypeError):
        return None


# ---------- 源1: apizero.cn（干净 Top10） ----------
def fetch_apizero():
    """返回干净的 Top10 列表。每个元素含 rank/name/box_office(万)/total_box/box_rate/show_rate/seat_rate/release_days"""
    url = "https://v1.apizero.cn/api/movie-box"
    r = get(url, timeout=15)
    out = {"ok": False, "list": [], "update_time": None}
    if r.status_code == 200:
        try:
            d = r.json()
            if d.get("code") == 0:
                data = d.get("data", {})
                out["list"] = data.get("list", [])
                out["update_time"] = data.get("update_time")
                out["ok"] = True
                log(f"  apizero: {len(out['list'])} 部影片, 更新时间 {out['update_time']}")
            else:
                log(f"  apizero 业务错误: code={d.get('code')} msg={d.get('msg')}")
        except Exception as e:
            log(f"  apizero 解析失败:", e)
    else:
        log(f"  apizero HTTP {r.status_code}")
    return out


# ---------- 源2: 中影票房网 ----------
def fetch_zgdypw():
    ts = int(time.time() * 1000)
    H = {"Referer": "https://www.zgdypw.cn/", "X-Requested-With": "XMLHttpRequest"}
    out = {"ok": False, "date": None, "films": [], "cities": [],
           "chains": [], "cinemas": [], "day_total": None,
           "trend7": [], "realtime": None}

    # 当日明细（在映前十 + 分布 + 大盘）
    r = get(f"https://www.zgdypw.cn/data/searchDayBoxOffice.json?timestamp={ts}", headers=H)
    if r.status_code == 200:
        try:
            d = r.json().get("data", {})
            out["date"] = d.get("businessDay")
            out["films"] = d.get("top10Films", []) or []
            out["cities"] = d.get("top10Citys", []) or []
            out["chains"] = d.get("top10CinemaChains", []) or []
            out["cinemas"] = d.get("top10Cinemas", []) or []
            db = d.get("dayBoxoffice", {})
            out["day_total"] = {
                "box": wan_to_yuan(db.get("totalBoxoffice")),
                "audience": db.get("totalAudience"),
                "session": db.get("totalSession"),
                "cinemaCount": db.get("cinemaCount"),
            }
            out["ok"] = True
        except Exception as e:
            log("searchDayBoxOffice 解析失败:", e)
    else:
        log("searchDayBoxOffice HTTP", r.status_code)

    # 近七日趋势
    r2 = get(f"https://www.zgdypw.cn/data/searchSevenDaysBoxOffice.json?timestamp={ts}", headers=H)
    if r2.status_code == 200:
        try:
            out["trend7"] = r2.json().get("data", []) or []
        except Exception as e:
            log("searchSevenDays 解析失败:", e)

    # 实时大盘
    r3 = get(f"https://www.zgdypw.cn/data/realtimedata.json?timestamp={ts}", headers=H)
    if r3.status_code == 200:
        try:
            d3 = r3.json()
            out["realtime"] = {
                "box": wan_to_yuan(d3.get("totalBoxoffice")),
                "audience": d3.get("totalAudience"),
                "session": d3.get("totalSession"),
                "service": d3.get("totalService"),
                "businessDay": d3.get("businessDay"),
            }
        except Exception as e:
            log("realtimedata 解析失败:", e)

    return out


# ---------- 源3: 猫眼专业版 ----------
def fetch_maoyan():
    """在映实时榜：movieInfo.movieName / movieId / sumBoxDesc(明文累计) / boxRate(明文占比)"""
    url = ("https://piaofang.maoyan.com/dashboard-ajax/movie"
           "?orderType=0&channelId=40009&sVersion=2")
    H = {"Referer": "https://piaofang.maoyan.com/dashboard"}
    r = get(url, headers=H)
    movies = {}
    if r.status_code == 200:
        try:
            lst = r.json().get("movieList", {}).get("list", [])
            for m in lst:
                info = m.get("movieInfo", {})
                mid = info.get("movieId")
                if not mid:
                    continue
                movies[str(mid)] = {
                    "name": info.get("movieName"),
                    "sumBoxDesc": info.get("sumBoxDesc"),      # 明文："16.35亿"
                    "sumBox": parse_cn_amount(info.get("sumBoxDesc")),
                    "boxRate": m.get("boxRate"),               # 明文："33.1%"
                    "avgSeatView": m.get("avgSeatView"),       # 明文："2.5%"
                    "showCount": m.get("showCount"),
                }
            log(f"  猫眼: {len(movies)} 部影片")
        except Exception as e:
            log("猫眼 dashboard-ajax 解析失败:", e)
    else:
        log("猫眼 dashboard-ajax HTTP", r.status_code)
    return movies


def enrich_movie(mid, name, movies_cache):
    """调用 maoyan.ahua.space 富集海报/类型/简介。按 movieId 缓存。返回扁平化 dict。"""
    if not mid:
        return {"name": name}
    key = str(mid)
    cached = movies_cache.get(key)
    if cached:
        rec = dict(cached)
        en = cached.get("enrich") or {}
        for k in ("poster", "category", "releaseDate", "summary", "duration"):
            if en.get(k) and not rec.get(k):
                rec[k] = en[k]
        if rec.get("poster"):
            return rec
    else:
        rec = {"name": name, "movieId": mid}
    try:
        r = get(f"https://maoyan.ahua.space/api/movie/{mid}",
                headers={"Referer": "https://maoyan.ahua.space/"})
        if r.status_code == 200:
            d = r.json()
            basic = d.get("basic", {}) or {}
            en = {
                "poster": basic.get("movieImg") or basic.get("poster") or basic.get("img"),
                "category": basic.get("category"),
                "releaseDate": basic.get("releaseDate"),
                "summary": (d.get("plot") or {}).get("summary"),
                "duration": basic.get("duration"),
            }
            rec.update({"name": basic.get("movieName") or name})
            rec.update({k: v for k, v in en.items() if v is not None})
            rec["enrich"] = en
            movies_cache[key] = rec
    except Exception as e:
        log(f"  富集 {name}({mid}) 失败:", e)
    return rec


# ============================================================
# 新增：影片评分 / 简介 四源富集
# ============================================================

def fetch_maoyan_rating(mid):
    """猫眼购票评分 + 简介。m.maoyan.com/mmdb/movie/v5/{id}.json -> sc(评分) / dra(简介)"""
    if not mid:
        return None
    try:
        r = get(f"https://m.maoyan.com/mmdb/movie/v5/{mid}.json",
                headers={"User-Agent": MOBILE_UA, "Referer": "https://m.maoyan.com/"})
        if r.status_code == 200:
            mv = (r.json().get("data") or {}).get("movie") or {}
            sc = mv.get("sc")
            if sc is None and mv.get("proScore"):
                sc = mv.get("proScore")          # 无观众评分时退而取专业评分
            return {
                "score": float(sc) if sc not in (None, 0, 0.0) else None,
                "url": f"https://m.maoyan.com/films/{mid}",
                "intro": (mv.get("dra") or "").strip() or None,
                "wish": mv.get("wish"),
                "ok": sc not in (None, 0, 0.0),
            }
    except Exception as e:
        log(f"  猫眼评分 {mid} 失败:", e)
    return None


def fetch_douban(name):
    """豆瓣评分 + 简介。三策略：
       ① subject_suggest 取 id -> rexxar JSON（轻量，首选）
       ② rexxar 失败 -> Playwright 浏览器渲染 subject 页（兜底，绕 JS 反爬）
    """
    did = None

    # ---- 策略①: suggest 取 id ----
    try:
        H = {"User-Agent": MOBILE_UA, "Accept": "application/json"}
        if DOUBAN_COOKIE:
            H["Cookie"] = DOUBAN_COOKIE
        r = get("https://movie.douban.com/j/subject_suggest?q=" + requests.utils.quote(name),
                headers=H)
        if r.status_code == 200:
            lst = r.json()
            if lst:
                for it in lst:
                    if it.get("title") == name:
                        did = it.get("id"); break
                if not did:
                    did = lst[0].get("id")
    except Exception as e:
        log(f"  豆瓣 suggest {name} 失败:", e)

    if not did:
        return None

    # ---- 策略①续: rexxar JSON ----
    last_err = None
    for attempt in range(3):
        try:
            rr = get(f"https://m.douban.com/rexxar/api/v2/movie/{did}",
                     headers={"User-Agent": MOBILE_UA,
                              "Referer": f"https://m.douban.com/movie/subject/{did}/"})
            if rr.status_code == 200:
                d = rr.json()
                rating = d.get("rating") or {}
                val = rating.get("value")
                has = val not in (None, 0, 0.0)
                return {
                    "score": float(val) if has else None,
                    "votes": rating.get("count"),
                    "url": f"https://movie.douban.com/subject/{did}/",
                    "summary": (d.get("summary") or "").strip() or None,
                    "ok": has,
                }
            last_err = f"HTTP{rr.status_code}"
        except Exception as e:
            last_err = str(e)
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))

    # ---- 策略②: Playwright 浏览器兜底 ----
    log(f"  豆瓣 {name} rexxar 失败({last_err})，尝试浏览器抓取...")
    try:
        import asyncio
        from playwright.async_api import async_playwright

        async def _browser_fetch():
            async with async_playwright() as p:
                b = await p.chromium.launch()
                pg = await b.new_page()
                await pg.goto(f"https://movie.douban.com/subject/{did}/",
                              wait_until="domcontentloaded", timeout=15000)
                await pg.wait_for_timeout(2500)
                rating = await pg.evaluate("""() => {
                    const el = document.querySelector('[property="v:average"]');
                    return el ? el.textContent.trim() : null;
                }""")
                summary = await pg.evaluate("""() => {
                    const el = document.querySelector('span[property="v:summary"]');
                    return el ? el.textContent.trim().slice(0,500) : null;
                }""")
                votes = await pg.evaluate("""() => {
                    const el = document.querySelector('[property="v:votes"]');
                    return el ? el.textContent.trim() : null;
                }""")
                await b.close()
                return {"rating": rating, "summary": summary, "votes": votes}

        result = asyncio.run(_browser_fetch())
        val = result.get("rating")
        if val and val not in ("", "无"):
            return {
                "score": float(val),
                "votes": result.get("votes"),
                "url": f"https://movie.douban.com/subject/{did}/",
                "summary": result.get("summary"),
                "ok": True,
            }
        log(f"  豆瓣 {name} 浏览器也未获取到评分")
    except Exception as e:
        log(f"  豆瓣 {name} 浏览器抓取失败:", e)

    return None


def fetch_tmdb(name):
    """TMDB 评分 + 简介（需 TMDB_KEY 或 TMDB_TOKEN）。"""
    key = TMDB_TOKEN or TMDB_KEY
    if not key:
        return None
    try:
        base = "https://api.themoviedb.org/3"
        hdr = {"Authorization": f"Bearer {TMDB_TOKEN}"} if TMDB_TOKEN else {}
        auth = f"api_key={TMDB_KEY}" if TMDB_KEY else None
        def url(path, extra=""):
            if auth:
                return f"{base}{path}?{auth}{extra}"
            return f"{base}{path}{extra}"
        r = get(url("/search/movie", "&query=" + requests.utils.quote(name)
                    + "&language=zh-CN&region=CN&include_adult=false"), headers=hdr)
        if r.status_code != 200:
            return None
        res = r.json().get("results") or []
        if not res:
            return None
        mid = res[0].get("id")
        r2 = get(url(f"/movie/{mid}", "&language=zh-CN"), headers=hdr)
        if r2.status_code != 200:
            return None
        d = r2.json()
        va = d.get("vote_average")
        return {
            "score": float(va) if va else None,
            "votes": d.get("vote_count"),
            "url": f"https://www.themoviedb.org/movie/{mid}",
            "overview": (d.get("overview") or "").strip() or None,
            "ok": bool(va),
        }
    except Exception as e:
        log(f"  TMDB {name} 失败:", e)
    return None


def _tao_token_from_cookie(cookie):
    """从 Cookie 中解析 __m_h5_tk 的 token 部分。"""
    m = re.search(r"__m_h5_tk=([^_;]+)", cookie)
    if not m:
        return None
    return m.group(1).split("_")[0]


def fetch_taopiaopiao(name):
    """淘票票评分（淘宝 mtop 签名，需 TAOPIAOPIAO_COOKIE，尽力而为）。"""
    if not TAO_COOKIE:
        return None
    token = _tao_token_from_cookie(TAO_COOKIE)
    secret = TAO_SECRET or "6972ef6ac9b180da32f6990234b3b339"  # 常见 h5 appSecret（可被环境变量覆盖）
    if not token:
        log("  淘票票: Cookie 中未找到 __m_h5_tk，跳过")
        return None
    try:
        appkey = "12574478"
        api = "mtop.com.taobao.booking.movie.search"
        t = str(int(time.time() * 1000))
        data = json.dumps({"q": name, "cityCode": "310100",
                           "pageIndex": 1, "pageSize": 5}, ensure_ascii=False)
        sign = hashlib.md5((token + "&" + t + "&" + secret + "&" + data).encode("utf-8")).hexdigest()
        u = (f"https://h5api.m.taobao.com/h5/{api}/1.0/?jsv=2.4.0&appKey={appkey}"
             f"&t={t}&sign={sign}&v=1.0&type=originaljson&data=" + requests.utils.quote(data))
        r = get(u, headers={"User-Agent": MOBILE_UA, "Cookie": TAO_COOKIE,
                            "Referer": "https://www.taopiaopiao.com/"})
        if r.status_code != 200:
            return None
        d = r.json()
        items = ((d.get("data") or {}).get("result") or {}).get("items") or []
        if not items:
            return None
        top = items[0]
        score = top.get("rating") or top.get("score") or top.get("audienceRating")
        return {
            "score": float(score) if score not in (None, "", 0) else None,
            "url": f"https://www.taopiaopiao.com/show/movie/{top.get('id')}.html",
            "ok": score not in (None, "", 0),
        }
    except Exception as e:
        log(f"  淘票票 {name} 失败:", e)
    return None


def load_ratings_cache():
    p = os.path.join(DATA, "ratings_cache.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_ratings(name, movieId, cache):
    """按 movieId(优先) 或 片名 取四源评分。逐源缓存：成功的源（含确无评分的结果）入库，
    失败的源（限流/网络）不入库，下一轮运行自动重试，保证最终完整性。"""
    key = str(movieId) if movieId else ("name:" + name)
    cached = cache.get(key, {})
    res = {"douban": None, "maoyan": None, "tmdb": None, "taopiaopiao": None}

    # 猫眼（按 movieId）
    if movieId:
        if cached.get("maoyan") is not None:
            res["maoyan"] = cached["maoyan"]
        else:
            res["maoyan"] = fetch_maoyan_rating(movieId)
            time.sleep(0.15)

    # 豆瓣（按片名，易限流，失败不缓存。间隔 3s 规避云 IP 封锁）
    if cached.get("douban") is not None:
        res["douban"] = cached["douban"]
    else:
        time.sleep(3)  # 豆瓣对数据中心 IP 限流严格，3s 间隔可稳定获取
        res["douban"] = fetch_douban(name)

    # TMDB（需密钥）
    if TMDB_KEY or TMDB_TOKEN:
        if cached.get("tmdb") is not None:
            res["tmdb"] = cached["tmdb"]
        else:
            res["tmdb"] = fetch_tmdb(name)

    # 淘票票（需 Cookie）
    if TAO_COOKIE:
        if cached.get("taopiaopiao") is not None:
            res["taopiaopiao"] = cached["taopiaopiao"]
        else:
            res["taopiaopiao"] = fetch_taopiaopiao(name)

    # 仅持久化有真实评分的源（ok=True 且 score 非 None）；
    # 无评分/限流/网络失败均不缓存，下次运行自动重试
    to_save = {}
    for s in res:
        v = res[s]
        if isinstance(v, dict) and v.get("ok") and v.get("score") is not None:
            to_save[s] = v
    if to_save:
        cache[key] = to_save
    return res


# ---------- 登录态接口（需 Cookie） ----------
def fetch_login_data(showing_list, date):
    """尝试用 MY_COOKIE 抓取 getBoxList / regionbox / 影院票房等登录态数据。"""
    result = {"has_cookie": bool(MY_COOKIE), "cinema_data": None,
              "province_data": None, "debug_files": []}

    if not MY_COOKIE:
        log("（未配置 MY_COOKIE）跳过登录态抓取")
        return result

    log("检测到 MY_COOKIE，尝试抓取登录态数据…")
    cookie_hdr = {"Cookie": MY_COOKIE, "Referer": "https://piaofang.maoyan.com/dashboard"}
    dbg_dir = os.path.join(DATA, "_debug")
    os.makedirs(dbg_dir, exist_ok=True)

    for params in [f"date={date}&sSplit=0", f"date={date}", f"token=&date={date}&split=0"]:
        url = f"https://piaofang.maoyan.com/dashboard-ajax/getBoxList?{params}"
        try:
            rr = get(url, headers=cookie_hdr, timeout=15)
            fname = f"getBoxList_{date.replace('-','')}.json"
            fpath = os.path.join(dbg_dir, fname)
            open(fpath, "w").write(rr.text)
            result["debug_files"].append(fname)
            log(f"  getBoxList ({params}) -> HTTP {rr.status_code} len={len(rr.text)}")
            if rr.status_code == 200 and len(rr.text) > 50:
                try:
                    d = rr.json()
                    result["cinema_data"] = d
                    log(f"  ✅ getBoxList 解析成功! keys={list(d.keys())[:20]}")
                except Exception:
                    log(f"  getBoxList 非 JSON（可能是 HTML 重定向到登录页）")
        except Exception as e:
            log(f"  getBoxList 失败:", e)

    for it in showing_list[:3]:
        mid = it.get("movieId")
        if not mid:
            continue
        for ep in [f"https://piaofang.maoyan.com/movie/{mid}/regionbox?date={date}",
                   f"https://piaofang.maoyan.com/dashboard-ajax/movie/regionbox?movieId={mid}&date={date}"]:
            try:
                rr = get(ep, headers=cookie_hdr, timeout=12)
                fname = f"region_{mid}_{date.replace('-','')}.json"
                open(os.path.join(dbg_dir, fname), "w").write(rr.text)
                result["debug_files"].append(fname)
                if rr.status_code == 200 and len(rr.text) > 30:
                    try:
                        rd = rr.json()
                        if result["province_data"] is None:
                            result["province_data"] = {}
                        result["province_data"][str(mid)] = rd
                        log(f"  ✅ regionbox {mid} -> keys={list(rd.keys())[:15]}")
                    except Exception:
                        pass
            except Exception as e:
                log(f"  regionbox 失败:", e)

    return result


# ---------- 主流程 ----------
def main():
    log("=== 三源融合 + 四源评分富集 爬虫启动 ===")

    az = fetch_apizero()   # 干净 Top10（明文当日票房）
    zg = fetch_zgdypw()    # 官方在映 + 分布 + 趋势
    my = fetch_maoyan()    # 累计票房 + movieId

    if not az["ok"] and not zg["ok"]:
        log("⚠️ 所有主数据源均失败，退出。")
        sys.exit(1)

    date = zg.get("date") or datetime.date.today().isoformat()
    year = int(str(date)[:4]) if date else datetime.date.today().year

    # 读取影片缓存 & 评分缓存
    movies_cache_path = os.path.join(DATA, "movies.json")
    movies_cache = {}
    if os.path.exists(movies_cache_path):
        try:
            movies_cache = json.load(open(movies_cache_path, encoding="utf-8"))
        except Exception:
            movies_cache = {}
    ratings_cache = load_ratings_cache()

    # 建立 name -> movieId 映射（猫眼）
    name_to_mid = {}
    for mid, mv in my.items():
        if mv.get("name"):
            name_to_mid[mv["name"]] = mid

    def match_mid(film_name):
        if film_name in name_to_mid:
            return name_to_mid[film_name]
        for nm, mid in name_to_mid.items():
            if film_name and (film_name in nm or nm in film_name):
                return mid
        return None

    # ---- 构建统一影片列表 ----
    film_map = {}

    # 1) apizero 骨架
    for m in az.get("list", []):
        nm = m.get("name")
        if not nm:
            continue
        mid = match_mid(nm)
        rec = enrich_movie(mid, nm, movies_cache)
        film_map[nm] = {
            "rank": m.get("rank"),
            "name": nm,
            "movieId": mid,
            "daySalesWan": m.get("box_office"),
            "daySalesYuan": wan_to_yuan(m.get("box_office")),
            "totalBoxDesc": m.get("total_box"),
            "totalBoxYuan": parse_cn_amount(m.get("total_box")),
            "boxRate": m.get("box_rate"),
            "showRate": m.get("show_rate"),
            "seatRate": m.get("seat_rate"),
            "releaseDays": m.get("release_days"),
            "poster": rec.get("poster"),
            "category": rec.get("category"),
            "releaseDate": rec.get("releaseDate"),
            "summary": rec.get("summary"),
            "_source": "apizero",
        }

    # 2) 中影网补充
    for f in zg.get("films", []):
        nm = f.get("filmName")
        if not nm:
            continue
        if nm in film_map:
            film_map[nm]["dayAudience"] = f.get("dayAudience")
            film_map[nm]["daySession"] = f.get("daySession")
            film_map[nm]["zgFilmTotalSales"] = wan_to_yuan(f.get("filmTotalSales"))
            if film_map[nm].get("_source") == "apizero":
                film_map[nm]["_source"] = "merged"
        else:
            mid = match_mid(nm)
            rec = enrich_movie(mid, nm, movies_cache)
            film_map[nm] = {
                "rank": f.get("rank"),
                "name": nm,
                "movieId": mid,
                "daySalesWan": None,
                "daySalesYuan": wan_to_yuan(f.get("daySales")),
                "cumYuan": wan_to_yuan(f.get("filmTotalSales")),
                "dayAudience": f.get("dayAudience"),
                "daySession": f.get("daySession"),
                "boxRate": (my.get(str(mid), {}).get("boxRate") if mid else None),
                "poster": rec.get("poster"),
                "category": rec.get("category"),
                "releaseDate": rec.get("releaseDate"),
                "summary": rec.get("summary"),
                "_source": "zgdypw",
            }

    # 3) 猫眼累计票房
    for mid_str, mv in my.items():
        nm = mv.get("name")
        if nm and nm in film_map:
            film_map[nm]["mySumBoxDesc"] = mv.get("sumBoxDesc")
            film_map[nm]["mySumBoxYuan"] = mv.get("sumBox")
            if not film_map[nm].get("boxRate"):
                film_map[nm]["boxRate"] = mv.get("boxRate")
            if not film_map[nm].get("movieId"):
                film_map[nm]["movieId"] = mid_str

    # 4) ★ 四源评分 / 简介 富集（写入 ratings + intro）
    have_tmdb = bool(TMDB_KEY or TMDB_TOKEN)
    have_tao = bool(TAO_COOKIE)
    log(f"评分富集：豆瓣+猫眼 默认开启；TMDB={'开' if have_tmdb else '关(需 TMDB_KEY)'}；"
        f"淘票票={'开' if have_tao else '关(需 TAOPIAOPIAO_COOKIE)'}")
    for nm, rec in film_map.items():
        mid = rec.get("movieId")
        rt = get_ratings(nm, mid, ratings_cache)
        # 归一化评分结构
        ratings = {}
        for src in ("douban", "maoyan", "tmdb", "taopiaopiao"):
            v = rt.get(src)
            if isinstance(v, dict) and v.get("ok") and v.get("score") is not None:
                ratings[src] = {"score": v["score"], "votes": v.get("votes"), "url": v.get("url")}
        rec["ratings"] = ratings
        # 简介优先级：TMDB > 豆瓣 > 猫眼(dra) > ahua(summary)
        intro, intro_src = None, None
        if rt.get("tmdb") and rt["tmdb"].get("overview"):
            intro, intro_src = rt["tmdb"]["overview"], "TMDB"
        elif rt.get("douban") and rt["douban"].get("summary"):
            intro, intro_src = rt["douban"]["summary"], "豆瓣"
        elif rt.get("maoyan") and rt["maoyan"].get("intro"):
            intro, intro_src = rt["maoyan"]["intro"], "猫眼"
        elif rec.get("summary"):
            intro, intro_src = rec["summary"], "猫眼"
        rec["intro"] = intro
        rec["intro_source"] = intro_src

    # ---- 排序生成在映前十 ----
    showing_list = sorted(film_map.values(),
                          key=lambda x: (x.get("daySalesYuan") or x.get("cumYuan") or 0),
                          reverse=True)
    for i, it in enumerate(showing_list[:30], 1):
        it["rank"] = i
    showing_list = showing_list[:30]

    # ---- 年度前十（累计近似）----
    yearly_candidates = sorted([f for f in film_map.values() if f.get("totalBoxYuan") or f.get("mySumBoxYuan") or f.get("zgFilmTotalSales")],
                               key=lambda x: (x.get("totalBoxYuan") or x.get("mySumBoxYuan") or x.get("zgFilmTotalSales") or 0),
                               reverse=True)
    yearly_list = []
    for i, it in enumerate(yearly_candidates[:10], 1):
        it_copy = dict(it)
        it_copy["rank"] = i
        yearly_list.append(it_copy)

    # ---- 分布（来自中影网官方）----
    def dist(items, name_key):
        return [{
            "rank": it.get("rank"),
            "name": it.get(name_key),
            "salesYuan": wan_to_yuan(it.get("totalSales")),
            "audience": it.get("dayAudience"),
            "session": it.get("daySession"),
        } for it in items]

    distribution = {
        "cities": dist(zg.get("cities", []), "cityName"),
        "chains": dist(zg.get("chains", []), "cinemaChainName"),
        "cinemas": dist(zg.get("cinemas", []), "cinemaName"),
    }

    # ---- 七日趋势 ----
    trend7 = [{
        "date": t.get("businessDay"),
        "boxYuan": wan_to_yuan(t.get("totalBoxoffice")),
        "audience": t.get("totalAudience"),
        "session": t.get("totalSession"),
        "cinemaCount": t.get("cinemaCount"),
    } for t in (zg.get("trend7") or [])]

    # ---- 登录态数据 ----
    login_result = fetch_login_data(showing_list, date)

    # ---- 评分来源统计 ----
    rated_count = {"douban": 0, "maoyan": 0, "tmdb": 0, "taopiaopiao": 0}
    for it in showing_list:
        for s in rated_count:
            if (it.get("ratings") or {}).get(s):
                rated_count[s] += 1
    intro_count = sum(1 for it in showing_list if it.get("intro"))

    # ---- 组装 BOXDATA ----
    srcs = [
        "apizero.cn（猫眼数据封装，Top10 明文当日票房）",
        "中影票房网 zgdypw.cn（国家电影专资办官方，城市/院线/影院分布+七日趋势）",
        "猫眼专业版 piaofang.maoyan.com（累计票房+影片匹配）",
        "猫眼 m.maoyan.com（购票评分+简介）",
        "豆瓣 movie.douban.com（评分+简介，rexxar JSON）",
    ]
    if have_tmdb:
        srcs.append("TMDB api.themoviedb.org（评分+简介，需密钥）")
    if have_tao:
        srcs.append("淘票票（评分，mtop 签名，需 Cookie）")

    BOXDATA = {
        "meta": {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": date,
            "year": year,
            "sources": srcs,
            "note": ("三源融合票房 + 四源评分/简介富集：猫眼(m.maoyan.com)购票评分、豆瓣(rexxar)评分与简介、"
                     "TMDB(需密钥)评分与简介、淘票票(需 Cookie)评分。点击榜单中的影片可查看评分对比与简介。"
                     "「年度前十」为【在映累计近似】口径，非严格本年度排名。"),
            "has_login_data": login_result["has_cookie"],
            "ratings_enabled": {
                "douban": True, "maoyan": True,
                "tmdb": have_tmdb, "taopiaopiao": have_tao,
            },
        },
        "showing": {
            "date": date,
            "apizero_update": az.get("update_time"),
            "list": showing_list,
        },
        "yearly": {
            "year": year,
            "note": ("近似口径：取在映影片累计总票房排序前十，"
                     "非严格年度（含跨年上映影片的历史累计）。"),
            "list": yearly_list,
        },
        "distribution": distribution,
        "trend7": trend7,
        "realtime": zg.get("realtime"),
        "day_total": zg.get("day_total"),
        "login_data": {
            "cinema_available": login_result["cinema_data"] is not None,
            "province_available": login_result["province_data"] is not None,
        },
        "movies": {str(k): v for k, v in movies_cache.items()},
    }

    # ---- 写出 ----
    js_content = "window.BOXDATA = " + json.dumps(BOXDATA, ensure_ascii=False) + ";"
    with open(os.path.join(DATA, "data.js"), "w", encoding="utf-8") as f:
        f.write(js_content)
    with open(os.path.join(DATA, "aggregate.json"), "w", encoding="utf-8") as f:
        json.dump(BOXDATA, f, ensure_ascii=False, indent=2)
    with open(movies_cache_path, "w", encoding="utf-8") as f:
        json.dump(movies_cache, f, ensure_ascii=False, indent=2)
    with open(os.path.join(DATA, "ratings_cache.json"), "w", encoding="utf-8") as f:
        json.dump(ratings_cache, f, ensure_ascii=False, indent=2)
    with open(os.path.join(HIST, f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(BOXDATA, f, ensure_ascii=False, indent=2)

    # 统计
    src_count = {}
    for f in showing_list:
        s = f.get("_source", "?")
        src_count[s] = src_count.get(s, 0) + 1

    log("✅ 三源融合 + 评分富集完成")
    log(f"   日期: {date}  在映: {len(showing_list)} 部  年度近似: {len(yearly_list)} 部")
    log(f"   评分覆盖(在映): 豆瓣 {rated_count['douban']} / 猫眼 {rated_count['maoyan']} / "
        f"TMDB {rated_count['tmdb']} / 淘票票 {rated_count['taopiaopiao']}；简介 {intro_count} 部")
    log(f"   来源分布: {src_count}")
    log(f"   城市/院线/影院: {len(distribution['cities'])}/{len(distribution['chains'])}/{len(distribution['cinemas'])}")
    log(f"   七日趋势: {len(trend7)} 天  富集影片: {sum(1 for v in movies_cache.values() if v.get('enrich'))}")
    log(f"   登录态: {'已配置' if MY_COOKIE else '未配置'} | "
        f"影院数据: {'有' if login_result['cinema_data'] else '无'} | "
        f"省份数据: {'有' if login_result['province_data'] else '无'}")


if __name__ == "__main__":
    main()
