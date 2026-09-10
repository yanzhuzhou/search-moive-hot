#!/usr/bin/env python3
"""CLI 启动脚本：python run_cli.py <关键词> [选项]"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from price_compare.cli import main

if __name__ == "__main__":
    sys.exit(main())
