"""本地 Web 服务器。

路由：
    GET  /api/demo       初始化示例（用演示数据跑一遍完整流水线）
    GET  /api/health     健康检查 + Playwright 状态 + cookie 已登录平台
    POST /api/search     现场运行采集脚本（支持 scraper_type=playwright/requests）
    GET  /               web/index.html
    GET  /web/*          静态资源
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from price_compare.cli import run_search          # noqa: E402
from price_compare import demo_data               # noqa: E402
from price_compare.processor import process       # noqa: E402
from price_compare.visualizer import to_payload   # noqa: E402

log = logging.getLogger("price_compare.server")
WEB_DIR = os.path.join(_HERE, "web")
COOKIE_DIR = Path(_HERE) / ".playwright_cookies"

_CONTENT_TYPE = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _playwright_status() -> dict:
    """汇总 Playwright 可用性 + cookie 登录状态。"""
    try:
        from price_compare.scrapers.playwright_scrapers import playwright_available
        pw_ok = playwright_available()
    except ImportError:
        pw_ok = False
    logged_in = []
    if COOKIE_DIR.is_dir():
        for f in COOKIE_DIR.glob("*.json"):
            logged_in.append(f.stem)
    return {"playwright_available": pw_ok, "logged_in_platforms": logged_in}


class Handler(BaseHTTPRequestHandler):
    server_version = "PriceCompare/2.0"

    def _send_json(self, status: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str) -> None:
        if not os.path.isfile(path):
            self._send_json(404, {"error": "not found", "path": path})
            return
        ext = os.path.splitext(path)[1].lower()
        ctype = _CONTENT_TYPE.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {"error": "invalid json"}

    def do_OPTIONS(self) -> None:
        self._send_json(200, {"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(os.path.join(WEB_DIR, "index.html"))
        elif path.startswith("/web/"):
            self._send_file(os.path.join(WEB_DIR, path[len("/web/"):]))
        elif path == "/api/demo":
            self._send_json(200, self._build_demo())
        elif path == "/api/health":
            self._send_json(200, {
                "status": "ok", "version": "2.0.0",
                "scraper": {"requests": True, **_playwright_status()},
            })
        else:
            self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/search":
            body = self._read_body_json()
            keyword = (body.get("keyword") or "").strip()
            if not keyword:
                self._send_json(400, {"error": "keyword 不能为空"})
                return
            limit = int(body.get("limit", 24) or 24)
            platforms = body.get("platforms") or ["jd", "taobao", "pinduoduo"]
            scraper = body.get("scraper", "requests")
            real = bool(body.get("real", False))
            taobao_cookie = body.get("taobao_cookie", "")
            jd_cookie = body.get("jd_cookie", "")
            pdd_anti = body.get("pdd_anti_content", "")
            try:
                payload = run_search(
                    keyword=keyword, limit=limit, platforms=platforms,
                    scraper_type=scraper, real=real,
                    jd_cookie=jd_cookie,
                    taobao_cookie=taobao_cookie, pdd_anti_content=pdd_anti)
                self._send_json(200, payload)
            except Exception as e:  # noqa: BLE001
                log.exception("search failed")
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found", "path": path})

    def _build_demo(self) -> dict:
        keyword = demo_data.DEFAULT_DEMO_KEYWORD
        raw = demo_data.generate(keyword, per_platform=6)
        products = process(raw)
        result = to_payload(keyword, products)
        return {
            "keyword": keyword,
            "sample_products": [p.to_dict() for p in raw],
            "result": result,
            "scraper_info": _playwright_status(),
        }

    def log_message(self, fmt, *args):
        log.debug("HTTP %s - %s", self.address_string(), fmt % args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="电商价格对比 Web 服务器")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not os.path.isdir(WEB_DIR):
        log.error("web 目录不存在: %s", WEB_DIR)
        return 1
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("演示服务启动: http://%s:%s (Ctrl+C)", args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("关闭服务")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
