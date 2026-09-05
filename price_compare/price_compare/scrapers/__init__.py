"""采集器集合。"""
from .base import BaseScraper, ScrapeError
from .jd import JDScraper
from .taobao import TaobaoScraper
from .pinduoduo import PinduoduoScraper

__all__ = ["BaseScraper", "ScrapeError", "JDScraper", "TaobaoScraper", "PinduoduoScraper"]
