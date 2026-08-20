"""爬虫任务后台线程（避免爬虫运行时卡住主窗口 UI）。

使用方法：

    worker = CrawlerWorker()
    worker.finished_ok.connect(my_success_handler)   # (VideoInfo) -> None
    worker.failed.connect(my_error_handler)          # (str) -> None
    worker.start()
"""

from __future__ import annotations

import time as _time

from PySide6.QtCore import QThread, Signal

from .bilibili import BilibiliCrawler, CrawlerError, DEFAULT_SPACE_URL, VideoInfo
from ..download_history import (
    DownloadRecord,
    forget_broken_entries,
    key_for_bilibili,
    lookup as history_lookup,
    record as history_record,
)


class CrawlerWorker(QThread):
    """在后台线程中执行 B 站最新视频抓取。"""

    # 抓取成功：传入 VideoInfo
    finished_ok = Signal(object)  # VideoInfo
    # 抓取失败：传入错误信息字符串
    failed = Signal(str)
    # 进度/日志消息：可用于弹气泡或打印
    log = Signal(str)

    def __init__(
        self,
        space_url: str = DEFAULT_SPACE_URL,
        proxy: str | None = None,
        headless: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._space_url = space_url
        self._proxy = proxy
        self._headless = headless

    def run(self) -> None:
        crawler = BilibiliCrawler(proxy=self._proxy, headless=self._headless)
        try:
            # 启动前顺手清一下"历史里有但磁盘上没文件"的死记录，避免命中后打开空文件
            try:
                cleaned = forget_broken_entries()
                if cleaned:
                    self.log.emit(f"清理了 {cleaned} 条下载历史里指向不存在文件的旧记录")
            except Exception:
                pass

            import re as _re

            self.log.emit("开始访问 UP 主空间，获取最新视频链接……")
            video_page_url, cookies, _wbi_keys = crawler.get_latest_video_url(self._space_url)
            self.log.emit(f"获取到视频页：{video_page_url}")

            m = _re.search(r"/video/(BV[0-9A-Za-z]+)", video_page_url or "")
            bvid = m.group(1) if m else ""

            # ---- 重复下载检测：命中 + 文件仍在磁盘 → 直接跳过"下载+合并"，只解析一次标题等字段给 UI 用 ----
            if bvid:
                rec = history_lookup(key_for_bilibili(bvid))
                if rec is not None:
                    self.log.emit(
                        f"⏭️  命中下载历史（bvid={bvid}）：{rec.output_path}"
                        f"（上次下载时间戳={rec.ts}），跳过本次下载，直接打开已存在文件"
                    )
                    # 解析一下最新 title 给 UI 展示（避免标题改过了还用老的），失败就用记录里的 title
                    try:
                        title, audio_url, video_url = crawler.get_video_info(video_page_url, cookies=cookies)
                        title = crawler._sanitize_filename(title)
                    except Exception:
                        title, audio_url, video_url = rec.title or "", "", ""
                    info = VideoInfo(
                        title=title or (rec.title or ""),
                        audio_url=audio_url,
                        video_url=video_url,
                        page_url=video_page_url,
                        bvid=bvid,
                        output_path=rec.output_path,
                    )
                    self.finished_ok.emit(info)
                    return

            # —— 新下载：用 get_latest_video_url 带回来的 cookies 直接跑"解析+下载+合并"，不再二次开 Selenium
            self.log.emit(f"未命中下载历史（bvid={bvid or '未知'}），开始下载并合并……")
            info: VideoInfo = crawler.download_video(video_page_url, cookies=cookies)
            self.log.emit(f"完成！输出文件：{info.output_path}")

            # 写入下载历史
            if info.bvid and info.output_path:
                try:
                    history_record(
                        key_for_bilibili(info.bvid),
                        DownloadRecord(
                            ts=int(_time.time()),
                            output_path=info.output_path,
                            title=info.title,
                            page_url=info.page_url,
                        ),
                    )
                except Exception as e:
                    self.log.emit(f"（非致命）写入 download_history.json 失败：{type(e).__name__}: {e}")

            self.finished_ok.emit(info)
        except CrawlerError as e:
            self.failed.emit(f"爬虫失败：{e}")
        except Exception as e:  # 兜底
            self.failed.emit(f"爬虫发生未预期错误：{type(e).__name__}: {e}")
