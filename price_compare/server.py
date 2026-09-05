"""本地 Web 演示服务器（纯标准库 http.server）。

提供：
    GET  /               -> web/index.html
    GET  /web/<file>     -> 静态资源
    GET  /api/demo       -> 初始化示例数据 + 对应分析结果
    POST /api/search     -> 现场运行采集脚本，返回 payload
    GET  /api/health      -> 健康检查

启动：
    python server.py [--host 0.0.0.0] [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# 让脚本既能从 price_compare/ 目录直接运行，也能被 -m 调用
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from price_compare.cli import run_search          # noqa: E402
from price_compare import demo_data               # noqa: E402
from price_compare.processor import process       # noqa: E402
from price_compare.visualizer import to_payload   # noqa: E402

log = logging.getLogger("price_compare.server")

WEB_DIR = os.path.join(_HERE, "web")

_CONTENT_TYPE = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "PriceCompare/1.0"

    # ---- 通用 ---------------------------------------------------------
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

    def do_OPTIONS(self) -> None:  # CORS preflight
        self._send_json(200, {"ok": True})

    # ---- 路由 ---------------------------------------------------------
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_file(os.path.join(WEB_DIR, "index.html"))
        elif path.startswith("/web/"):
            name = path[len("/web/"):]
            self._send_file(os.path.join(WEB_DIR, name))
        elif path == "/api/demo":
            self._send_json(200, self._build_demo())
        elif path == "/api/health":
            self._send_json(200, {"status": "ok", "version": "1.0.0"})
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
            real = bool(body.get("real", False))
            try:
                payload = run_search(
                    keyword=keyword, limit=limit, platforms=platforms, real=real)
                self._send_json(200, payload)
            except Exception as e:  # noqa: BLE001
                log.exception("search failed")
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(404, {"error": "not found", "path": path})

    def _build_demo(self) -> dict:
        """初始化示例：原始演示数据 + 处理后的分析结果。"""
        keyword = demo_data.DEFAULT_DEMO_KEYWORD
        raw = demo_data.generate(keyword, per_platform=6)
        products = process(raw)
        result = to_payload(keyword, products)
        return {
            "keyword": keyword,
            "sample_products": [p.to_dict() for p in raw],   # 未处理的示例数据
            "result": result,                                 # 对应的处理结果
            "note": "初始化示例数据（演示）。在上方输入关键词并点击「开始采集」可现场运行脚本。",
        }

    # 静音访问日志
    def log_message(self, fmt, *args):
        log.debug("HTTP %s - %s", self.address_string(), fmt % args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="电商价格对比 - 演示 Web 服务器")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址")
    parser.add_argument("--port", type=int, default=8000, help="端口")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not os.path.isdir(WEB_DIR):
        log.error("web 目录不存在: %s", WEB_DIR)
        return 1
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("演示服务启动: http://%s:%s (Ctrl+C 退出)", args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log.info("收到退出信号，关闭服务")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
