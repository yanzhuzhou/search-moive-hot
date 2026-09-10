"""Web 演示页后端（标准库 http.server，零额外依赖）。

提供：
    GET  /                  → 演示首页（含示例数据初始化）
    GET  /api/sample        → 预置示例关键词的结果（首屏展示）
    GET  /api/compare?kw=.. → 现场运行采集脚本，返回 JSON 结果
    GET  /api/charts?kw=..  → 现场运行的图表 HTML 片段

运行：
    python run_web.py
然后浏览器打开 http://localhost:8787/
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import os

from price_compare import CompareEngine
from price_compare.engine import CompareResult

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.join(_HERE, "static")
_DEMO_KEYWORD = "蓝牙耳机"
_engine = CompareEngine()

# 启动时预生成示例数据，首屏直接展示
_sample_result: CompareResult | None = None
_sample_lock = threading.Lock()


def _get_sample() -> CompareResult:
    global _sample_result
    if _sample_result is None:
        with _sample_lock:
            if _sample_result is None:
                _sample_result = _engine.run(_DEMO_KEYWORD, per_platform=8)
    return _sample_result


def _result_to_json(r: CompareResult) -> dict:
    return {
        "keyword": r.keyword,
        "raw_count": r.raw_count,
        "count": len(r.products),
        "summary": r.summary,
        "products": [p.to_dict() for p in r.products],
    }


def _build_data_example() -> dict:
    """构造"数据示例 + 结果示例"对照，供首屏展示采集→清洗的转化。

    展示每个平台的一条原始字段（真实接口字段名）与其归一化后的 Product 字段，
    让用户直观理解适配器的作用。
    """
    from price_compare.adapters.jd import JDAdapter
    from price_compare.adapters.taobao import TaobaoAdapter
    from price_compare.adapters.pdd import PDDAdapter
    import random
    from price_compare.adapters.base import _seed_from

    kw = _DEMO_KEYWORD
    pairs = []
    for adapter_cls in (JDAdapter, TaobaoAdapter, PDDAdapter):
        ad = adapter_cls()
        rng = random.Random(_seed_from(kw, salt=ad.platform))
        raw = ad._make_one_mock(rng, kw, 0)
        p = ad.normalize(raw, kw)
        pairs.append({
            "platform": ad.platform,
            "raw": raw,                       # 平台原生字段（数据示例）
            "normalized": p.to_dict() if p else None,  # 归一化结果（结果示例）
        })
    return {
        "keyword": kw,
        "description": "每个平台采集到的原始字段（左）与适配器归一化后的统一字段（右）",
        "pairs": pairs,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 简化日志
        pass

    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str):
        full = os.path.join(_STATIC_DIR, path)
        if not os.path.isfile(full):
            self.send_error(404, "Not Found")
            return
        with open(full, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1].lower()
        ctype = {".js": "application/javascript", ".css": "text/css"}.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            with open(os.path.join(_HERE, "templates", "index.html"), "r", encoding="utf-8") as f:
                self._send_html(f.read())
            return

        if path == "/static/app.js" or path.startswith("/static/"):
            self._send_static(path.replace("/static/", "", 1) if path.startswith("/static/") else "app.js")
            return

        if path == "/api/sample":
            self._send_json(_result_to_json(_get_sample()))
            return

        if path == "/api/data-example":
            self._send_json(_build_data_example())
            return

        if path == "/api/compare":
            kw = (qs.get("kw", [""])[0] or "").strip()
            if not kw:
                self._send_json({"error": "参数 kw 不能为空"}, status=400)
                return
            try:
                r = _engine.run(kw, per_platform=8)
                self._send_json(_result_to_json(r))
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if path == "/api/charts":
            kw = (qs.get("kw", [""])[0] or "").strip()
            if not kw:
                # 返回示例图表
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(_get_sample().chart_html.encode("utf-8"))
                return
            r = _engine.run(kw, per_platform=8)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(r.chart_html.encode("utf-8"))
            return

        self.send_error(404, "Not Found")


def serve(host: str = "0.0.0.0", port: int = 8787):
    # 预热示例数据，避免首屏等待
    _get_sample()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"→ 电商价格对比演示页已启动：http://localhost:{port}/")
    print(f"  示例关键词：{_DEMO_KEYWORD}（首屏预置展示）")
    print(f"  Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
        server.shutdown()


if __name__ == "__main__":
    serve()
