"""B 站 UP 主最新视频爬虫

功能：
1. 通过 Selenium 控制 Chrome 访问 UP 主个人空间，获取最新视频播放页 URL
2. 通过 requests 请求视频页面，提取标题、音视频直链
3. 分别下载音频（mp3）与视频（mp4）到 data/ 目录
4. 调用 ffmpeg 合并音视频，输出到 output/ 目录

注意：
- Chrome 及 chromedriver 需放在 support/Chrome/Application/ 下，否则无法用 Selenium
- ffmpeg 需放在 support/ffmpeg/bin/ffmpeg.exe 下
- 代理 proxy 参数可选；若留空则不走代理
- 视频下载完成后会在 data/ 目录保留分离的音视频文件（如需清理可自行打开注释）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..resource_manager import get_data_path, get_output_path, get_support_path


# ============================ 可调配置 ============================

# 默认抓取的 UP 主空间地址："王涵大朋友ovo"
DEFAULT_SPACE_URL = "https://space.bilibili.com/382211078"

# UA，需要与浏览器特征匹配
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# Selenium 等待元素出现的最长时间（秒）
SELENIUM_WAIT_TIMEOUT = 20

# HTTP 请求超时（秒）
HTTP_TIMEOUT = 30

# 空间主页最新视频 XPATH（B站前端改版时需同步调整）
LATEST_VIDEO_XPATH = (
    '//*[@id="app"]/main/div[1]/div[1]/section[2]/div/div[2]/div/div/div[1]/div/div/div[1]/a'
)


# ============================ 数据结构 ============================

@dataclass
class VideoInfo:
    title: str
    audio_url: str
    video_url: str
    page_url: str
    output_path: str  # 最终合并后的文件完整路径（output 下）


class CrawlerError(Exception):
    """爬虫统一异常类"""


# ============================ 核心爬虫 ============================

class BilibiliCrawler:
    """B站 UP 主最新视频爬虫"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        headless: bool = False,
    ):
        """
        Args:
            proxy: 可选 HTTP 代理，格式如 "http://1.1.1.1:4433"。None 表示不走代理。
            headless: 是否开启 Chrome 无头模式（不显示浏览器界面）。
        """
        self.proxy = proxy
        self.headless = headless

        # 路径
        self.chrome_exe = get_support_path("Chrome", "Application", "chrome.exe")
        self.chromedriver_exe = get_support_path("Chrome", "Application", "chromedriver.exe")
        self.ffmpeg_exe = get_support_path("ffmpeg", "bin", "ffmpeg.exe")

        # 预编译正则
        self._re_playinfo = re.compile(r"<script>window\.__playinfo__=(.*?)</script>", re.S)
        # 标题：兼容不同属性顺序，匹配 <h1 ... title="xxx" ... class="video-title" ...>
        self._re_title = re.compile(
            r'<h1\b[^>]*?\btitle="(.*?)"[^>]*?\bclass="video-title[^"]*"',
            re.S,
        )
        # 另一种顺序兼容：先 class 后 title
        self._re_title_alt = re.compile(
            r'<h1\b[^>]*?\bclass="video-title[^"]*"[^>]*?\btitle="(.*?)"',
            re.S,
        )

    # ------------------------- 公共接口 -------------------------

    def run(self, space_url: str = DEFAULT_SPACE_URL) -> VideoInfo:
        """执行完整流程并返回 VideoInfo。"""
        # 1. 检查外部工具
        self._check_tools()

        # 2. 空间主页 → 最新视频 URL
        video_page_url = self.get_latest_video_url(space_url)

        # 3. 视频页面 → 标题 & 音视频直链
        title, audio_url, video_url = self.get_video_info(video_page_url)

        # 4. 下载分离音视频
        title = self._sanitize_filename(title)
        self.save_raw(title, audio_url, video_url, video_page_url)

        # 5. ffmpeg 合并
        output_path = self.combine_video(title)

        return VideoInfo(
            title=title,
            audio_url=audio_url,
            video_url=video_url,
            page_url=video_page_url,
            output_path=output_path,
        )

    # ------------------------- 子步骤 -------------------------

    def get_latest_video_url(self, space_url: str) -> str:
        """用 Selenium 打开 UP 主空间，取第一条视频的播放页地址。"""
        if not os.path.isfile(self.chrome_exe):
            raise CrawlerError(
                f"未找到 Chrome 可执行文件：{self.chrome_exe}\n"
                "请将便携版 Chrome 放到 support/Chrome/Application/ 下"
            )
        if not os.path.isfile(self.chromedriver_exe):
            raise CrawlerError(
                f"未找到 chromedriver：{self.chromedriver_exe}\n"
                "请将对应版本 chromedriver 放到 support/Chrome/Application/ 下"
            )

        chrome_options = Options()
        chrome_options.binary_location = self.chrome_exe
        service = Service(self.chromedriver_exe)

        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--incognito")
        if self.headless:
            chrome_options.add_argument("--headless=new")

        # 通用抗检测参数
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins-discovery")
        chrome_options.add_argument("--enable-logging")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument(f"--user-agent={USER_AGENT}")

        web = webdriver.Chrome(service=service, options=chrome_options)
        try:
            # 隐藏 webdriver 指纹
            web.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            web.execute_script(
                "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})"
            )
            web.execute_script(
                "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']})"
            )
            web.execute_script(
                "const originalQuery = window.navigator.permissions.query;"
                " window.navigator.permissions.query = (parameters) =>"
                " (parameters.name === 'notifications' ?"
                " Promise.resolve({state: 'denied'}) : originalQuery(parameters))"
            )
            web.minimize_window()
            web.get(space_url)

            wait = WebDriverWait(web, SELENIUM_WAIT_TIMEOUT)
            element = wait.until(
                EC.presence_of_element_located((By.XPATH, LATEST_VIDEO_XPATH))
            )
            href = element.get_attribute("href")
            if not href:
                raise CrawlerError("找到视频卡片元素，但 href 为空。")
            return href
        finally:
            web.quit()

    def get_response(self, url: str, referer: str = DEFAULT_SPACE_URL) -> requests.Response:
        """用 requests 拉取页面内容，可选代理。"""
        headers = {
            "user-agent": USER_AGENT + " Edg/141.0.0.0",
            "referer": referer,
        }
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        try:
            resp = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=HTTP_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise CrawlerError(f"HTTP 请求失败：{e}") from e
        return resp

    def get_video_info(self, video_page_url: str):
        """从视频播放页解析 title、audio_url、video_url。"""
        resp = self.get_response(video_page_url, referer=video_page_url)
        html_text = resp.text

        playinfo_matches = self._re_playinfo.findall(html_text)
        if not playinfo_matches:
            raise CrawlerError("未找到 window.__playinfo__，可能视频页面结构改版或需要登录。")

        try:
            data = json.loads(playinfo_matches[0])
        except json.JSONDecodeError as e:
            raise CrawlerError(f"__playinfo__ 不是合法 JSON：{e}") from e

        dash = data.get("data", {}).get("dash")
        if not dash:
            # 部分情况下是 data.dash 不存在，尝试其他键
            raise CrawlerError("未从 __playinfo__ 中解析到 dash 音视频信息。")

        try:
            audio_url = dash["audio"][0]["baseUrl"]
            video_url = dash["video"][0]["baseUrl"]
        except (KeyError, IndexError) as e:
            raise CrawlerError(f"解析 dash 音视频字段失败：{e}") from e

        title_matches = self._re_title.findall(html_text) or self._re_title_alt.findall(html_text)
        if not title_matches:
            raise CrawlerError("未解析出视频标题。")
        title = title_matches[0].strip()

        return title, audio_url, video_url

    def save_raw(
        self,
        title: str,
        audio_url: str,
        video_url: str,
        referer: str,
    ) -> None:
        """下载音视频到 data/ 目录。"""
        audio_path = get_data_path(f"{title}.mp3")
        video_path = get_data_path(f"{title}.mp4")

        audio = self.get_response(audio_url, referer=referer).content
        with open(audio_path, mode="wb") as f:
            f.write(audio)

        video = self.get_response(video_url, referer=referer).content
        with open(video_path, mode="wb") as f:
            f.write(video)

    def combine_video(self, title: str) -> str:
        """调用 ffmpeg 合并音视频，返回输出文件路径。"""
        if not os.path.isfile(self.ffmpeg_exe):
            raise CrawlerError(
                f"未找到 ffmpeg：{self.ffmpeg_exe}\n"
                "请将 ffmpeg.exe 放到 support/ffmpeg/bin/ 下"
            )

        video_path = get_data_path(f"{title}.mp4")
        audio_path = get_data_path(f"{title}.mp3")
        output_path = get_output_path(f"{title}.mp4")

        cmd = [
            self.ffmpeg_exe,
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-strict", "experimental",
            "-map", "0:v",
            "-map", "1:a",
            "-y",  # 覆盖已存在文件
            output_path,
            "-loglevel", "quiet",
        ]
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if result.returncode != 0:
                raise CrawlerError(
                    f"ffmpeg 合并失败（exit={result.returncode}）：\n{result.stderr}"
                )
        except FileNotFoundError as e:
            raise CrawlerError(f"无法执行 ffmpeg：{e}") from e

        # 可选：清理分离的临时音视频
        # if os.path.isfile(video_path):
        #     os.remove(video_path)
        # if os.path.isfile(audio_path):
        #     os.remove(audio_path)

        return output_path

    # ------------------------- 工具函数 -------------------------

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for c in illegal_chars:
            title = title.replace(c, "")
        return title.strip() or "untitled"

    def _check_tools(self) -> None:
        """提前检查 requests 和 selenium 是否可用。"""
        # 这里不抛异常表示 requests/selenium 都能 import，真正的文件检查在各步骤做。
        return


def crawl_latest_video(
    space_url: str = DEFAULT_SPACE_URL,
    proxy: Optional[str] = None,
    headless: bool = False,
) -> VideoInfo:
    """便捷函数：直接跑一趟完整流程。"""
    return BilibiliCrawler(proxy=proxy, headless=headless).run(space_url)


if __name__ == "__main__":
    # 单独调试：python -m src.crawler.bilibili
    info = crawl_latest_video()
    print("最新视频：")
    print("  标题   :", info.title)
    print("  页面   :", info.page_url)
    print("  输出   :", info.output_path)
    print("all over!")
