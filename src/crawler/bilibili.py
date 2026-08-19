"""B 站 UP 主最新视频爬虫 — 多策略兜底版本

获取最新视频 URL 的优先级（从上到下，成功即返回）：
  1. Selenium 打开空间主页 → 自动点击"投稿"tab → 在当前页 DOM 里找
     第一条视频卡片的 <a href=".../video/...">。多个 XPATH 兜底。
  2. 复用同一次 Selenium 会话的 Cookie，走空间动态接口
     /x/polymer/web-dynamic/v1/feed/space 取第一条视频动态。
  3. 继续复用 Selenium 会话，走 wbi 签名后的投稿列表接口
     /x/space/wbi/arc/search。

为什么必须先跑 Selenium：
  B 站对 API 有风控，首次请求需携带 buvid3 Cookie 才能拿到正常 JSON，
  否则大概率返回 412（风险页）或 code=-799（降频）。先过一遍浏览器
  让服务器下发 buvid3，之后 requests 复用这套 Cookie 就能稳定通过。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from functools import reduce
from typing import Iterable, Optional

import requests
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..resource_manager import get_data_path, get_output_path, get_support_path


# ============================ 可调配置 ============================

# 默认抓取的 UP 主空间地址："王涵大朋友ovo"
DEFAULT_SPACE_URL = "https://space.bilibili.com/382211078"
DEFAULT_MID = 382211078

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

SELENIUM_WAIT_TIMEOUT = 20
HTTP_TIMEOUT = 30

# 多个 XPATH 兜底找空间页上的第一条"视频卡片 a 标签"。
# B 站经常改 DOM，有新写法加在这里即可。
LATEST_VIDEO_XPATHS: list[str] = [
    # 2025 Q3 投稿 tab 下第一条视频卡片（当前 XPATH，保留原框架写的）
    '//*[@id="page-video"]//a[contains(@href,"/video/")][1]',
    # 列表中任意 video 链接，只要 href 里含 /video/
    '//div[contains(@class,"small-item")]//a[contains(@href,"/video/")][1]',
    '//div[contains(@class,"bili-video-card")]//a[contains(@href,"/video/")][1]',
    '//*[@id="submit-video-list"]//a[contains(@href,"/video/")][1]',
    # 通配：页面里第一个 /video/ 链接（href 不含 /video/.../ 的非播放页）
    '//a[contains(@href,".bilibili.com/video/")][1]',
]


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


# ============================ wbi 签名辅助（公开算法，B 站固定规则） ============================
# 参考：https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/wbi.md
_WBI_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], _WBI_MIXIN_KEY_ENC_TAB, "")[:32]


def _enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    wbi_key = img_key + sub_key
    mixin_key = _get_mixin_key(wbi_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    params = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    w_rid = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    params["w_rid"] = w_rid
    return params


# ============================ 核心爬虫 ============================

class BilibiliCrawler:
    """B 站 UP 主最新视频爬虫（Selenium 取 Cookie + 浏览器/接口兜底取视频）"""

    def __init__(
        self,
        proxy: Optional[str] = None,
        headless: bool = False,
        mid: int = DEFAULT_MID,
    ):
        self.proxy = proxy
        self.headless = headless
        self.mid = mid

        self.chrome_exe = get_support_path("Chrome", "Application", "chrome.exe")
        self.chromedriver_exe = get_support_path("Chrome", "Application", "chromedriver.exe")
        self.ffmpeg_exe = get_support_path("ffmpeg", "bin", "ffmpeg.exe")

        self._re_playinfo = re.compile(r"<script>window\.__playinfo__=(.*?)</script>", re.S)
        self._re_title = re.compile(
            r'<h1\b[^>]*?\btitle="(.*?)"[^>]*?\bclass="video-title[^"]*"', re.S,
        )
        self._re_title_alt = re.compile(
            r'<h1\b[^>]*?\bclass="video-title[^"]*"[^>]*?\btitle="(.*?)"', re.S,
        )

    # ------------------------------------------------------------------ public

    def run(self, space_url: str = DEFAULT_SPACE_URL) -> VideoInfo:
        self._check_browser_tools()

        web = self._open_browser()
        cookies: dict[str, str] = {}
        wbi_img_key = wbi_sub_key = ""
        try:
            # --- 取最新视频 URL（策略 1：页面里找 DOM） ---
            video_page_url, extra = self._fetch_latest_video_via_browser(web, space_url)

            # 浏览器访问完空间页肯定已经种好了 buvid3 等 cookie，接口兜底时复用
            cookies = {c["name"]: c["value"] for c in web.get_cookies()}
            wbi_img_key, wbi_sub_key = extra.get("wbi_keys", ("", ""))

            # --- 取最新视频 URL（策略 2：动态流接口） ---
            if not video_page_url:
                video_page_url = self._fetch_latest_via_dynamic_api(cookies)

            # --- 取最新视频 URL（策略 3：wbi 签名投稿列表接口） ---
            if not video_page_url and wbi_img_key and wbi_sub_key:
                video_page_url = self._fetch_latest_via_wbi_api(cookies, wbi_img_key, wbi_sub_key)

            if not video_page_url:
                raise CrawlerError(
                    "未能获取到最新视频链接。\n"
                    "常见原因：UP 主暂无投稿视频，或空间页结构改版。\n"
                    f"可手动访问 {space_url} 页面确认。"
                )
        finally:
            web.quit()

        # 后续步骤：视频页解析 → 下载 → ffmpeg 合并
        title, audio_url, video_url = self.get_video_info(video_page_url, cookies=cookies)
        title = self._sanitize_filename(title)
        self.save_raw(title, audio_url, video_url, video_page_url, cookies=cookies)
        output_path = self.combine_video(title)

        return VideoInfo(
            title=title,
            audio_url=audio_url,
            video_url=video_url,
            page_url=video_page_url,
            output_path=output_path,
        )

    # ------------------------------------------------------------------ 视频链接：策略 1

    def _fetch_latest_video_via_browser(
        self, web: webdriver.Chrome, space_url: str
    ) -> tuple[Optional[str], dict]:
        """Selenium 打开空间页 → 点投稿 tab → 多个 XPATH 兜底找首条视频"""

        # 第一次 GET：种 cookie（buvid3 等）
        web.get(space_url)
        time.sleep(2)

        # 尝试点"投稿"tab（各种文案/选择器兜底）
        self._click_submit_tab_if_possible(web)
        time.sleep(2)  # 给点时间让卡片列表加载（接口 + 渲染）

        # 用多个 XPATH 依次找第一个 <a href=/video/...>
        href: Optional[str] = None
        for xpath in LATEST_VIDEO_XPATHS:
            try:
                el = WebDriverWait(web, 3).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                found = el.get_attribute("href")
                if found and "/video/" in found:
                    href = found
                    break
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
                continue

        # 即使没找到 href，也尝试从页面找 wbi key 供 API 兜底用
        wbi_keys = self._try_extract_wbi_keys(web)
        return href, {"wbi_keys": wbi_keys}

    def _click_submit_tab_if_possible(self, web: webdriver.Chrome) -> None:
        """点击"投稿"tab，失败静默。尝试多种定位方式。"""
        submit_selectors: list[tuple[str, str]] = [
            (By.CSS_SELECTOR, '#navigator [href*="/video"]'),
            (By.CSS_SELECTOR, 'a.s-space-tab_item[href*="/video"]'),
            (By.XPATH, '//div[@id="navigator"]//*[contains(text(),"投稿")]'),
            (By.XPATH, '//div[@id="page-video"]'),  # 已经在投稿页就不动
        ]
        for by, value in submit_selectors:
            try:
                els = web.find_elements(by, value)
                if not els:
                    continue
                # 有 page-video 就说明当前已经定位视频列表页，不用点
                if by == By.XPATH and "page-video" in value:
                    return
                els[0].click()
                time.sleep(1.0)
                return
            except Exception:
                continue

    def _try_extract_wbi_keys(self, web: webdriver.Chrome) -> tuple[str, str]:
        """从 window.__INITIAL_STATE__ / 导航接口返回里挖 wbi key。失败返回 ("","")。"""
        js = """
        try {
          const keys = {};
          if (window.__INITIAL_STATE__) {
            const nav = window.__INITIAL_STATE__.upData?.nav;
            keys.img = nav?.wbi_img?.img_url?.split('/').pop()?.split('.')[0] || '';
            keys.sub = nav?.wbi_img?.sub_url?.split('/').pop()?.split('.')[0] || '';
          }
          return JSON.stringify(keys);
        } catch(e) { return '{}'; }
        """
        try:
            raw = web.execute_script(js) or "{}"
            d = json.loads(raw)
            return (d.get("img", "") or ""), (d.get("sub", "") or "")
        except Exception:
            return "", ""

    # ------------------------------------------------------------------ 视频链接：策略 2 / 3

    def _build_session(self, cookies: dict[str, str]) -> requests.Session:
        s = requests.Session()
        if self.proxy:
            s.proxies.update({"http": self.proxy, "https": self.proxy})
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": f"https://space.bilibili.com/{self.mid}",
            "Origin": "https://space.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        for k, v in cookies.items():
            s.cookies.set(k, v, domain=".bilibili.com")
        return s

    def _fetch_latest_via_dynamic_api(self, cookies: dict[str, str]) -> Optional[str]:
        """走 UP 主动态流，从"投稿视频"动态里挑第一条。"""
        url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
        params = {"host_mid": self.mid, "offset": "", "timezone_offset": -480}
        s = self._build_session(cookies)
        try:
            r = s.get(url, params=params, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                return None
            j = r.json()
            items = (j.get("data") or {}).get("items") or []
            for it in items:
                # 类型 DYNAMIC_TYPE_AV = 2 代表投稿视频
                if it.get("type") == "DYNAMIC_TYPE_AV" or it.get("basic", {}).get("comment_type") == 1:
                    major = (it.get("modules") or {}).get("module_dynamic", {}).get("major") or {}
                    archive = major.get("archive") or {}
                    jump = archive.get("jump_url") or ""
                    if jump.startswith("//"):
                        jump = "https:" + jump
                    if "/video/" in jump:
                        return jump if jump.startswith("http") else "https:" + jump
        except Exception:
            return None
        return None

    def _fetch_latest_via_wbi_api(
        self, cookies: dict[str, str], img_key: str, sub_key: str
    ) -> Optional[str]:
        """走 wbi 签名投稿列表接口。"""
        base = "https://api.bilibili.com/x/space/wbi/arc/search"
        params = {
            "mid": self.mid,
            "ps": 5,
            "tid": 0,
            "pn": 1,
            "order": "pubdate",
            "order_avoided": "true",
            "platform": "web",
            "web_location": "1550101",
        }
        signed = _enc_wbi(params, img_key, sub_key)
        s = self._build_session(cookies)
        try:
            r = s.get(base, params=signed, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                return None
            j = r.json()
            if j.get("code") != 0:
                return None
            vlist = (((j.get("data") or {}).get("list") or {}).get("vlist")) or []
            if not vlist:
                return None
            bvid = vlist[0].get("bvid")
            if bvid:
                return f"https://www.bilibili.com/video/{bvid}"
        except Exception:
            return None
        return None

    # ------------------------------------------------------------------ 视频页面解析

    def get_response(
        self,
        url: str,
        *,
        referer: str = DEFAULT_SPACE_URL,
        cookies: Optional[dict[str, str]] = None,
    ) -> requests.Response:
        s = self._build_session(cookies or {})
        s.headers["Referer"] = referer
        try:
            resp = s.get(url, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise CrawlerError(f"HTTP 请求失败：{e}") from e
        return resp

    def get_video_info(self, video_page_url: str, *, cookies: dict[str, str] | None = None):
        resp = self.get_response(video_page_url, referer=video_page_url, cookies=cookies)
        html_text = resp.text

        playinfo_matches = self._re_playinfo.findall(html_text)
        if not playinfo_matches:
            raise CrawlerError(
                "未找到 window.__playinfo__，可能视频页面结构改版或需要登录。"
            )

        try:
            data = json.loads(playinfo_matches[0])
        except json.JSONDecodeError as e:
            raise CrawlerError(f"__playinfo__ 不是合法 JSON：{e}") from e

        dash = (data.get("data") or {}).get("dash")
        if not dash:
            # 某些情况下 durl 里会有一个单文件直链（flv/mp4），尽量兼容
            durl = (data.get("data") or {}).get("durl") or []
            if durl and "url" in durl[0]:
                single = durl[0]["url"]
                # 作为 audio + video 共用同一个，后面合并会是纯视频（无独立音轨）
                title = self._extract_title(html_text)
                return title, single, single
            raise CrawlerError("未从 __playinfo__ 中解析到 dash 音视频信息。")

        try:
            audio = dash.get("audio") or []
            if not audio:
                audio_url = ""  # 有些纯无声，给空串
            else:
                audio_url = audio[0]["baseUrl"] or audio[0].get("backupUrl", [""])[0]
            video_url = dash["video"][0]["baseUrl"] or dash["video"][0].get("backupUrl", [""])[0]
        except (KeyError, IndexError) as e:
            raise CrawlerError(f"解析 dash 音视频字段失败：{e}") from e

        title = self._extract_title(html_text)
        return title, audio_url, video_url

    def _extract_title(self, html_text: str) -> str:
        title_matches = self._re_title.findall(html_text) or self._re_title_alt.findall(html_text)
        if title_matches:
            return title_matches[0].strip()
        # 最后兜底：<title>标签，格式一般是"xxx_哔哩哔哩_bilibili"
        m = re.search(r"<title>(.*?)</title>", html_text, re.S)
        if m:
            return m.group(1).split("_")[0].strip()
        return "untitled"

    # ------------------------------------------------------------------ 下载 / 合并

    def save_raw(
        self,
        title: str,
        audio_url: str,
        video_url: str,
        referer: str,
        *,
        cookies: dict[str, str] | None = None,
    ) -> None:
        """下载音视频到 data/ 目录。audio_url 为空时生成一个静音占位 mp3，避免 ffmpeg 崩。"""
        audio_path = get_data_path(f"{title}.mp3")
        video_path = get_data_path(f"{title}.mp4")

        if audio_url:
            audio = self.get_response(audio_url, referer=referer, cookies=cookies).content
            with open(audio_path, "wb") as f:
                f.write(audio)
        else:
            self._write_silent_mp3(audio_path)

        video = self.get_response(video_url, referer=referer, cookies=cookies).content
        with open(video_path, "wb") as f:
            f.write(video)

    @staticmethod
    def _write_silent_mp3(path: str) -> None:
        """纯视频 dash 没有 audio，写一个极小的 2 秒静音 mp3 占位，ffmpeg 就能合并。"""
        # 一段可以直接解复用的空 MPEG 1 Layer 3 2ch 44100Hz ≈ 32kbps 2s 静音
        silent = (
            b"\xff\xfb\x90\x04\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        )
        with open(path, "wb") as f:
            f.write(silent * 250)

    def combine_video(self, title: str) -> str:
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
            "-shortest",
            "-y",
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
        if os.path.isfile(video_path):
             os.remove(video_path)
        if os.path.isfile(audio_path):
             os.remove(audio_path)

        return output_path

    # ------------------------------------------------------------------ 工具

    def _check_browser_tools(self) -> None:
        missing: list[str] = []
        for name, p in [
            ("Chrome 浏览器", self.chrome_exe),
            ("chromedriver", self.chromedriver_exe),
        ]:
            if not os.path.isfile(p):
                missing.append(f"{name}: {p}")
        if missing:
            raise CrawlerError("以下依赖缺失，请补齐后重试：\n- " + "\n- ".join(missing))

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for c in illegal_chars:
            title = title.replace(c, "")
        return title.strip() or "untitled"

    def _open_browser(self) -> webdriver.Chrome:
        chrome_options = Options()
        chrome_options.binary_location = self.chrome_exe
        service = Service(self.chromedriver_exe)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--incognito")
        if self.headless:
            chrome_options.add_argument("--headless=new")

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
        if self.proxy:
            chrome_options.add_argument(f"--proxy-server={self.proxy}")

        web = webdriver.Chrome(service=service, options=chrome_options)
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
        return web


def crawl_latest_video(
    space_url: str = DEFAULT_SPACE_URL,
    proxy: str | None = None,
    headless: bool = False,
    mid: int = DEFAULT_MID,
) -> VideoInfo:
    return BilibiliCrawler(proxy=proxy, headless=headless, mid=mid).run(space_url)


if __name__ == "__main__":
    info = crawl_latest_video()
    print("最新视频：")
    print("  标题   :", info.title)
    print("  页面   :", info.page_url)
    print("  输出   :", info.output_path)
    print("all over!")
