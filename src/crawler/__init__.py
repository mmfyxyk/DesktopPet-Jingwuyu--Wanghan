"""爬虫模块（拓展功能）

包含 B 站 / 抖音等平台的视频抓取脚本。
"""

from .bilibili import (
    BilibiliCrawler,
    DEFAULT_SPACE_URL,
    crawl_latest_video,
)
from .worker import CrawlerWorker
from .douyin import (
    DEFAULT_SEC_UID,
    DouyinCrawler,
    DouyinLoginRequired,
    DouyinVideo,
)

__all__ = [
    "BilibiliCrawler",
    "CrawlerWorker",
    "DEFAULT_SEC_UID",
    "DEFAULT_SPACE_URL",
    "DouyinCrawler",
    "DouyinLoginRequired",
    "DouyinVideo",
    "crawl_latest_video",
]
