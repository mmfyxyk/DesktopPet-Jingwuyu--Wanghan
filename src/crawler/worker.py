"""爬虫任务后台线程（避免爬虫运行时卡住主窗口 UI）。

使用方法：

    worker = CrawlerWorker()
    worker.finished_ok.connect(my_success_handler)   # (VideoInfo) -> None
    worker.failed.connect(my_error_handler)          # (str) -> None
    worker.start()
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .bilibili import BilibiliCrawler, CrawlerError, DEFAULT_SPACE_URL, VideoInfo


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
            self.log.emit("开始访问 UP 主空间，获取最新视频链接……")
            video_page_url = crawler.get_latest_video_url(self._space_url)
            self.log.emit(f"获取到视频页：{video_page_url}")

            self.log.emit("解析视频页，提取音视频地址……")
            title, audio_url, video_url = crawler.get_video_info(video_page_url)
            title = crawler._sanitize_filename(title)
            self.log.emit(f"视频标题：{title}")

            self.log.emit("下载音视频分离文件……")
            crawler.save_raw(title, audio_url, video_url, video_page_url)

            self.log.emit("调用 ffmpeg 合并音视频……")
            output_path = crawler.combine_video(title)

            info = VideoInfo(
                title=title,
                audio_url=audio_url,
                video_url=video_url,
                page_url=video_page_url,
                output_path=output_path,
            )
            self.log.emit(f"完成！输出文件：{output_path}")
            self.finished_ok.emit(info)
        except CrawlerError as e:
            self.failed.emit(f"爬虫失败：{e}")
        except Exception as e:  # 兜底
            self.failed.emit(f"爬虫发生未预期错误：{type(e).__name__}: {e}")
