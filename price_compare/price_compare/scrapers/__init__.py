"""采集器集合。"""
from .base import BaseScraper, ScrapeError
from .jd import JDScraper
from .taobao import TaobaoScraper
from .pinduoduo import PinduoduoScraper

__all__ = ["BaseScraper", "ScrapeError", "JDScraper", "TaobaoScraper", "PinduoduoScraper"]


def make_scraper(platform: str, scraper_type: str = "requests", **kwargs) -> BaseScraper:
    """工厂：根据平台和采集器类型创建采集器实例。

    Args:
        platform: "jd" / "taobao" / "pinduoduo"
        scraper_type: "requests" (默认) / "playwright"
        **kwargs: 传给采集器的额外参数（cookie、anti_content 等）
    """
    if scraper_type == "playwright":
        try:
            from .playwright_scrapers import (
                PlaywrightJDScraper, PlaywrightTaobaoScraper, PlaywrightPinduoduoScraper,
            )
            cls_map = {
                "jd": PlaywrightJDScraper,
                "taobao": PlaywrightTaobaoScraper,
                "pinduoduo": PlaywrightPinduoduoScraper,
            }
            return cls_map[platform](allow_real=True, **kwargs)
        except ImportError as e:
            raise ScrapeError(
                f"Playwright 模式需要先安装: pip install playwright && playwright install chromium (错误: {e})")
    # 默认 requests 模式
    cls_map = {
        "jd": JDScraper,
        "taobao": TaobaoScraper,
        "pinduoduo": PinduoduoScraper,
    }
    cls = cls_map[platform]
    if platform == "taobao":
        return cls(allow_real=True, cookie=kwargs.get("taobao_cookie", ""))
    if platform == "pinduoduo":
        return cls(allow_real=True, anti_content=kwargs.get("pdd_anti_content", ""))
    return cls(allow_real=True)
