"""采集器基类。

设计要点：
1. 统一接口 search(keyword, limit) -> list[Product]；
2. 提供带超时、UA 伪装、重试的 _http_get 工具方法（基于 urllib，纯标准库）；
3. 真实采集失败时，由各子类的 _fallback 返回演示数据，并在记录上标注 source=demo，
   保证工具在受限环境下仍可端到端运行；
4. 每次采集记录耗时与来源，便于审计。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from ..models import Product

log = logging.getLogger("price_compare.scrapers")


class ScrapeError(RuntimeError):
    pass


class BaseScraper:
    """平台采集器基类。"""
    name: str = "base"
    platform_cn: str = "基类"
    search_url_template: str = ""

    def __init__(self, timeout: float = 8.0, retries: int = 1,
                 allow_real: bool = True) -> None:
        self.timeout = timeout
        self.retries = retries
        self.allow_real = allow_real
        self.stats: dict[str, Any] = {"attempted": False, "real_count": 0,
                                     "demo_count": 0, "elapsed_ms": 0,
                                     "source": "none"}

    # ---- 公共接口 -------------------------------------------------------
    def search(self, keyword: str, limit: int = 20) -> list[Product]:
        if not keyword.strip():
            return []
        start = time.time()
        self.stats["attempted"] = True
        products: list[Product] = []
        if self.allow_real:
            try:
                products = self._fetch(keyword, limit)
                self.stats["source"] = "real"
                self.stats["real_count"] = len(products)
            except (ScrapeError, Exception) as e:  # noqa: BLE001
                log.warning("[%s] 真实采集失败，回退演示数据: %s", self.name, e)
                products = self._fallback(keyword, limit)
                self.stats["source"] = "demo"
                self.stats["demo_count"] = len(products)
        else:
            products = self._fallback(keyword, limit)
            self.stats["source"] = "demo"
            self.stats["demo_count"] = len(products)
        self.stats["elapsed_ms"] = round((time.time() - start) * 1000, 1)
        return products[:limit]

    # ---- 子类实现 -------------------------------------------------------
    def _fetch(self, keyword: str, limit: int) -> list[Product]:
        """真实抓取，子类重写。失败抛 ScrapeError。"""
        raise ScrapeError("未实现真实采集")

    def _fallback(self, keyword: str, limit: int) -> list[Product]:
        """演示数据回退。"""
        from .. import demo_data
        all_demo = demo_data.generate(keyword, per_platform=8)
        mine = [p for p in all_demo if p.platform == self.platform_cn]
        for p in mine:
            p.extra["fallback_reason"] = "real_scrape_unavailable"
        return mine[:limit]

    # ---- HTTP 工具 -----------------------------------------------------
    def _http_get(self, url: str, headers: dict[str, str] | None = None,
                  params: dict[str, str] | None = None) -> str:
        """带 UA 伪装、超时、重试的 GET 请求。"""
        if params:
            q = urllib.parse.urlencode(params)
            url = f"{url}{'&' if '?' in url else '?'}{q}"
        h = {
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if headers:
            h.update(headers)
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, headers=h, method="GET")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = resp.read()
                    enc = resp.headers.get_content_charset() or "utf-8"
                    return data.decode(enc, errors="replace")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = e
                log.debug("[%s] HTTP 第 %d 次失败: %s", self.name, attempt + 1, e)
                time.sleep(0.5 * (attempt + 1))
        raise ScrapeError(f"HTTP 失败: {last_err}")

    def _http_get_json(self, url: str, headers: dict[str, str] | None = None,
                       params: dict[str, str] | None = None) -> Any:
        body = self._http_get(url, headers=headers, params=params)
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            raise ScrapeError(f"JSON 解析失败: {e}") from e
