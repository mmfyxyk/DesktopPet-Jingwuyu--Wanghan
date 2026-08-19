"""爬虫模块（拓展功能）

包含 B 站等平台的视频抓取脚本。
后期新增的爬虫（抖音、ihan 等）请放到本目录下新建对应文件。
"""

from .bilibili import (
    BilibiliCrawler,
    DEFAULT_SPACE_URL,
    crawl_latest_video,
)
from .worker import CrawlerWorker

__all__ = [
    "BilibiliCrawler",
    "CrawlerWorker",
    "DEFAULT_SPACE_URL",
    "crawl_latest_video",
]
