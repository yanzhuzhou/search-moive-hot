#!/usr/bin/env python3
"""Web 演示页启动脚本：python run_web.py，访问 http://localhost:8787/"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.app import serve

if __name__ == "__main__":
    port = 8787
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    serve(port=port)
