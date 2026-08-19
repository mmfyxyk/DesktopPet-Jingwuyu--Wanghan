"""抖音爬虫 — 登录态复用 + 接口兜底 + 首登引导框架（可扩展）

背景：抖音首页、用户主页、aweme 视频详情页，在未登录情况下：
  1) 接口大概率返回 "需要登录" / has_more=false / 空数据；
  2) 视频直链 URL 需要带 a_bogus/xbogus 参数（签名每次请求都要算）。

方案（完全不需要把你的账号密码写进代码）：
  第 0 步（一次性）：运行 `python tools/douyin_first_login.py`，它会
    - 用 support/Chrome/Application/chrome.exe
    - 打开一个 **带用户数据目录的窗口**：support/Chrome/Profile-Douyin
    - 页面会自动跳抖音「登录」入口。你用手机 App 扫码登录一次。
    - 登录完成后，浏览器里能看到个人头像/昵称就算成功。
    - 回到程序窗口按「已登录，完成」脚本会把 Cookie 从 profile 中提取
      再另存为 data/douyin_cookies.json，同时 profile 本身也保留了登录态。

  之后每次爬取：
    - 如果 user-data-dir 里已经登录过 → 直接复用，不需要再扫码；
    - 若 Cookie 过期 → 用 data/douyin_cookies.json 注入 selenium session，
      再访问 https://www.douyin.com/ 刷新 msToken；
    - 仍不行 → 再弹一次「重新扫码登录」窗口，流程同上。

  视频列表 / 下载两条路径二选一：
    A) 纯接口：访问 www.douyin.com/aweme/v1/web/aweme/post/ 拿到 aweme_list
       → 解析 video.bit_rate[0].play_addr 直链，requests 下载。
       但抖音会要求请求带 `a_bogus` 或 `X-Bogus`（JS 签名），纯 Python
       实现不稳，不推荐走这条路。
    B) 稳定方案（推荐，本框架内默认走这个）：
       - 接口只负责收集最新视频的 aweme_id / 网页 URL 列表；
       - 下载交给 `yt-dlp` + cookies.txt（Netscape 格式）。yt-dlp 内置了
         对抖音签名 / 反爬的长期跟进维护，几乎不会坏。
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Iterable, Optional

import requests

# selenium 相关（本框架已在 support 放了便携版 Chrome/chromedriver）
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..resource_manager import get_data_path, get_output_path, get_support_path


DEFAULT_SEC_UID = "MS4wLjABAAAALFdBYwOJ_j1XRBnO_qbxPfcDl2OMKGcACPIZ4Glpp1k"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class DouyinLoginRequired(Exception):
    """需要用户完成一次扫码登录再重试"""


@dataclass
class DouyinVideo:
    aweme_id: str
    web_url: str          # 播放页：https://www.douyin.com/video/{aweme_id}
    desc: str              # 作品标题/描述
    cover_url: str = ""


class DouyinCrawler:
    """抖音 UP 主最新作品爬虫（登录态依赖便携 Chrome 用户数据目录）。"""

    # 登录态存放的三处路径（给 GUI 展示 / 一键清理时枚举）
    LOGIN_LOCATIONS_DESC = {
        "chrome_profile_dir": "便携 Chrome 的独立用户资料目录（缓存、Cookie、localStorage 都在里面，最完整）",
        "cookies_json":       "data/douyin_cookies.json（Selenium / requests 注入用，从 profile 提取的快照）",
        "cookies_netscape":   "data/douyin_cookies.txt（yt-dlp 下载时 --cookies 需要的 Netscape 格式）",
    }

    def __init__(
        self,
        sec_uid: str = DEFAULT_SEC_UID,
        headless: bool = False,
        proxy: Optional[str] = None,
    ):
        self.sec_uid = self.normalize_sec_uid(sec_uid)
        self.headless = headless
        self.proxy = proxy

        self.chrome_exe = get_support_path("Chrome", "Application", "chrome.exe")
        self.chromedriver_exe = get_support_path("Chrome", "Application", "chromedriver.exe")
        # 用户数据目录：独立于 support/Chrome/Default，不跟爬虫 B 站混用
        self.user_data_dir = get_support_path("Chrome", "Profile-Douyin")
        os.makedirs(self.user_data_dir, exist_ok=True)

        # Cookie：双持久化（profile 本身一份 + data/douyin_cookies.json 一份）
        self.cookie_file = get_data_path("douyin_cookies.json")
        self.cookie_jar_netscape = get_data_path("douyin_cookies.txt")

    # ------------------------------------------------------------------ utils

    @classmethod
    def normalize_sec_uid(cls, uid_or_url: str) -> str:
        """支持传两种：
        1) 直接传 sec_uid：MS4wLjABAAAA... （抖音 web 主页 /user/ 后面的字符串）
        2) 传完整的主页 URL：https://www.douyin.com/user/MS4wLjABAAAA...
           或带分享尾参 /?previous_page=... 这种。

        任何一种都能自动抽取 sec_uid，用户不用自己手工抠。
        """
        s = (uid_or_url or "").strip()
        if not s:
            return s
        # URL 里 /user/xxx 的情况
        for needle in ["/user/", "?sec_uid=", "&sec_uid="]:
            if needle in s:
                after = s.split(needle, 1)[1]
                # 去掉后续路径 / 查询串 / 锚点
                candidate = after.split("?", 1)[0].split("&", 1)[0].split("#", 1)[0].split("/", 1)[0]
                if candidate:
                    return candidate
        # 兜底：用户直接贴的就是 sec_uid（几乎都是 MS4wLjAB 开头）
        return s

    def login_data_locations(self) -> dict[str, str]:
        """返回当前实例三个登录数据所在的绝对路径（给 UI 弹窗展示）。"""
        return {
            "chrome_profile_dir": self.user_data_dir,
            "cookies_json":       self.cookie_file,
            "cookies_netscape":   self.cookie_jar_netscape,
        }

    def clear_login_data(self) -> list[str]:
        """一键删除这 3 处。返回成功删除的条目列表。

        GUI 用这个做「退出登录」。删除前会先断言没有 selenium 进程占用
        profile_dir（由调用方负责把后台线程先停掉）。
        """
        import shutil
        removed: list[str] = []
        locs = self.login_data_locations()

        # 1) Profile 目录最占体积，用 shutil.rmtree
        d = locs["chrome_profile_dir"]
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                removed.append(f"profile_dir  {d}")
            except OSError:  # 比如被 Chrome.exe 占用
                try:
                    os.makedirs(d, exist_ok=True)  # 清不掉就跳过，让返回里说明
                except OSError:
                    pass
        # 2) json
        for key in ("cookies_json", "cookies_netscape"):
            f = locs[key]
            if os.path.isfile(f):
                try:
                    os.remove(f)
                    removed.append(f"{key:<17} {f}")
                except OSError:
                    pass
        return removed

    # ------------------------------------------------------------------ tools

    def _build_options(self) -> Options:
        opts = Options()
        opts.binary_location = self.chrome_exe
        # 关键：user-data-dir 让 Chrome 记住登录态（Cookie、localStorage 全在里面）
        opts.add_argument(f"--user-data-dir={self.user_data_dir}")
        # 抖音对无痕识别很严 → 不要 --incognito
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument(f"--user-agent={USER_AGENT}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        if self.proxy:
            opts.add_argument(f"--proxy-server={self.proxy}")
        return opts

    def _open_browser(self, *, foreground: bool = False) -> webdriver.Chrome:
        """打开便携版 Chrome。

        foreground:
            False（默认）：登录态已存在、直接去爬列表的场景 → 最小化，不打扰用户。
            True：登录场景 / 需要用户扫码 / 人机交互时 → **放大前台 + 前置**，让用户看得见。
        """
        if not os.path.isfile(self.chrome_exe) or not os.path.isfile(self.chromedriver_exe):
            raise DouyinLoginRequired(
                "缺少 support/Chrome/Application/chrome(.exe) 或 chromedriver.exe"
            )
        service = Service(self.chromedriver_exe)
        driver = webdriver.Chrome(service=service, options=self._build_options())
        # 隐藏 webdriver 指纹（CDP），抖音比 B 站更在意这个
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
                    "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});"
                    "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;"
                    "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;"
                    "delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;"
                )
            },
        )
        if foreground:
            try:
                driver.maximize_window()
            except Exception:
                pass
            try:
                # CDP 把浏览器前置（Windows 下比 setattr 更稳）
                driver.execute_cdp_cmd(
                    "Browser.setWindowBounds",
                    {"windowId": 1, "bounds": {"windowState": "normal"}},
                )
            except Exception:
                pass
        else:
            try:
                driver.minimize_window()
            except Exception:
                pass
        return driver

    # ------------------------------------------------------------------ login

    def ensure_login(self, max_wait_sec: int = 300, *, foreground: bool = True) -> None:
        """**纯阻塞式登录（不应该被 GUI 场景的 CrawlWorker 直接调用）**。

        正确用法（GUI）：
          菜单「登录/重新登录（扫码）」→ 由 DouyinLoginWorker 调 _open_browser(foreground=True)
          并通过 user_action_required 信号弹 GUI 确认框等待用户扫码。
        遗留兼容（终端脚本 tools/douyin_first_login.py）：
          仍可直接调本方法，但会 print 日志 + WebDriverWait 轮询。
        """
        driver = self._open_browser(foreground=foreground)
        try:
            # 直接打开首页：未登录时首页右上角会自然出现"登录"按钮或弹二维码
            # （不走 /passport/web/user/login 这个内部旧 URL，改版后会返回"非法用户"）
            driver.get("https://www.douyin.com/")
            driver.implicitly_wait(5)

            self._detect_fatal_page(driver)

            already_logged_in = self._check_logged_in(driver)
            if already_logged_in:
                self._dump_cookies(driver)
                return

            print(
                "[抖音爬虫] 请在弹出的 Chrome 窗口中用抖音 App 扫码登录。\n"
                f"[抖音爬虫] 登录成功后程序将在 {max_wait_sec}s 内自动检测并继续。"
            )

            WebDriverWait(driver, max_wait_sec, 2).until(
                lambda d: self._check_logged_in(d)
            )
            self._dump_cookies(driver)
        finally:
            driver.quit()

    @staticmethod
    def _detect_fatal_page(driver) -> None:
        """抖音改版后有些 URL 会落在"非法用户/链接失效/404"页，立刻抛异常不要等死等。"""
        # 允许 DOM 先渲染
        import time
        time.sleep(1.5)
        src = driver.page_source or ""
        url_now = driver.current_url or ""
        fatal_hits = ["非法用户", "链接失效", "页面不存在", "404 Not Found", "Page Not Found"]
        hit = next((h for h in fatal_hits if h in src), None)
        if hit:
            raise DouyinLoginRequired(
                f"抖音打开失败：页面里出现「{hit}」(当前URL: {url_now})。\n"
                "常见原因：\n"
                "  1) 用了被抖音废弃的登录入口；本程序已经改成跳首页，请再试一次。\n"
                "  2) 当前账号/IP触发风控；换个网络再试 / 或者扫码登录后直接正常浏览。"
            )

    @staticmethod
    def _check_logged_in(driver) -> bool:
        """三态判定：已登录=True / 未登录=False / 页面异常=抛异常 / 未知=False 继续等。"""
        try:
            # 先看页面会不会本身是"非法用户"
            # 先兜底看 cookie：sessionid / sessionid_ss 任意一个就是登录态
            cookies = {c["name"]: c.get("value", "") for c in driver.get_cookies()}
            if cookies.get("sessionid") or cookies.get("sessionid_ss"):
                return True
            # DOM 判定：登录后右上角有自己头像（class 里含 avatar），或者有带 nickname 的文本元素
            # 登录按钮出现 → 明确是未登录，返回 False 继续等
            login_btns = driver.find_elements(
                By.XPATH,
                "//*[self::div or self::button or self::span or self::a][contains(normalize-space(text()), '登录') and string-length(normalize-space(text())) <= 10]",
            )
            has_login_btn = any(e.is_displayed() for e in login_btns)
            avatar_eles = driver.find_elements(By.CSS_SELECTOR, 'img[class*="avatar"]')
            has_avatar = any(e.is_displayed() for e in avatar_eles)
            if has_avatar and not has_login_btn:
                return True
            # 还不确定 → 返回 False（由上层等）
            return False
        except DouyinLoginRequired:
            raise
        except Exception:
            return False

    def _dump_cookies(self, driver) -> None:
        cookies = driver.get_cookies()
        # 1) JSON 格式，方便直接注入 requests.Session
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        # 2) Netscape 格式，直接给 yt-dlp --cookies douyin_cookies.txt 用
        jar = MozillaCookieJar(self.cookie_jar_netscape)
        for c in cookies:
            # MozillaCookieJar 需要 domain/path 合法；过滤掉缺失字段的
            if not c.get("domain") or not c.get("path"):
                continue
            expires = int(c.get("expiry") or (2**31 - 1))
            from http.cookiejar import Cookie
            jar.set_cookie(Cookie(
                version=0,
                name=c["name"],
                value=c.get("value", ""),
                port=None, port_specified=False,
                domain=c["domain"], domain_specified=True,
                domain_initial_dot=c["domain"].startswith("."),
                path=c["path"], path_specified=True,
                secure=bool(c.get("secure")),
                expires=expires,
                discard=False,
                comment=None, comment_url=None,
                rest={"HttpOnly": c.get("httpOnly", "")},
                rfc2109=False,
            ))
        jar.save(ignore_discard=True, ignore_expires=True)

    def _load_session(self) -> requests.Session:
        """用 douyin_cookies.json 构建 requests.Session（若没 cookies 先抛登录异常）。"""
        if not os.path.isfile(self.cookie_file):
            raise DouyinLoginRequired(
                "未找到 data/douyin_cookies.json，请先执行 ensure_login() 完成首次扫码登录。"
            )
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": f"https://www.douyin.com/user/{self.sec_uid}",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with open(self.cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        for c in cookies:
            s.cookies.set(c["name"], c.get("value", ""), domain=c.get("domain") or ".douyin.com", path=c.get("path") or "/")
        if self.proxy:
            s.proxies.update({"http": self.proxy, "https": self.proxy})
        return s

    # ------------------------------------------------------------------ list videos

    def list_latest_videos(self, count: int = 10) -> list[DouyinVideo]:
        """爬取 UP 主主页最新作品。

        **重要**：本函数不再自动阻塞调 ensure_login；没 Cookie 或主页显示"未登录"时会直接
        抛 DouyinLoginRequired。GUI 场景下，先让用户通过菜单「登录/重新登录（扫码）」完成
        一次性扫码（DouyinLoginWorker 处理），保存了 3 处登录态后再调用本函数。
        """
        # 如果连 cookie 文件都还没生成，说明没做过登录引导，直接报给 UI 引导用户去菜单登录
        if not os.path.isfile(self.cookie_file):
            raise DouyinLoginRequired(
                "尚未登录抖音，无法获取作品列表。\n"
                "请先使用菜单：拓展功能 → 抖音 → 登录/重新登录（扫码） 完成一次扫码登录。"
            )

        # 爬取场景：已经登录过 → 默认后台最小化不打扰
        driver = self._open_browser(foreground=False)
        try:
            driver.get(f"https://www.douyin.com/user/{self.sec_uid}")
            # 1) 页面里出现"非法用户/不存在" → sec_uid 错了或账号被限制，立刻抛
            self._detect_fatal_page(driver)

            # 2) 检查当前是不是"被要求登录"状态（有些私密用户/风控会在主页上强制出登录弹窗）
            if not self._check_logged_in(driver):
                # 已经有 cookie 但首页判定未登录，多半是 cookie 过期 / 被刷新无效
                raise DouyinLoginRequired(
                    "抖音登录态已过期（有 Cookie 文件但页面判定未登录）。\n"
                    "请使用菜单：拓展功能 → 抖音 → 清除登录数据（退出登录），然后再做一次 登录/重新登录（扫码）。"
                )

            # 3) 等作品卡片。没登录 / 权限不够 的话 20s 超时也不会死卡
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/video/"]'))
                )
            except Exception:
                pass

            # 4) 从页面里拿多少算多少
            hrefs: list[str] = []
            for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]'):
                href = a.get_attribute("href") or ""
                if href and "/video/" in href and href not in hrefs:
                    hrefs.append(href)
            results: list[DouyinVideo] = []
            for href in hrefs[:count]:
                aweme_id = self._aweme_id_from_url(href)
                if not aweme_id:
                    continue
                try:
                    desc = (a.text or "").strip() or aweme_id
                except Exception:
                    desc = aweme_id
                results.append(DouyinVideo(
                    aweme_id=aweme_id,
                    web_url=href,
                    desc=desc,
                ))
            # 刷新一次 cookie（sessionid 可能被刷新）
            try:
                self._dump_cookies(driver)
            except Exception:
                pass
            if results:
                return results
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        raise DouyinLoginRequired(
            "在已登录的 Chrome 里没解析到作品列表。\n"
            "常见原因：\n"
            "  1) sec_uid 不对 / 账号被限制（私密 / 风控）。\n"
            "  2) 登录态过期，需要重新扫码。\n"
            "建议步骤：先 清除登录数据 → 重新登录（扫码） 后再试。"
        )

    @staticmethod
    def _aweme_id_from_url(url: str) -> str:
        for part in url.replace("?", "/").split("/"):
            if len(part) == 19 and part.isdigit():  # 新版 aweme_id 是 19 位数字
                return part
        # 兜底：取最后一段纯数字
        for token in url.rstrip("/").split("/")[::-1]:
            if token.isdigit() and token:
                return token
        return ""

    # ------------------------------------------------------------------ download

    def download_with_ytdlp(self, video: DouyinVideo, out_dir: Optional[str] = None) -> str:
        """推荐下载方式：yt-dlp + Netscape cookies.txt，自动处理 a_bogus 签名。

        安装：pip install yt-dlp，并在 docs/requirements.txt 打开对应行。
        """
        out_dir = out_dir or get_output_path("douyin")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        yt_dlp_cmd = [
            sys_executable(),
            "-m", "yt_dlp",
            "--cookies", self.cookie_jar_netscape,
            "--no-check-certificate",
            "-o", os.path.join(out_dir, "%(title).80s [%(id)s].%(ext)s"),
            video.web_url,
        ]
        try:
            result = subprocess.run(
                yt_dlp_cmd, check=False, capture_output=True, text=True,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"找不到 yt-dlp，先 pip install yt-dlp：{e}")

        if result.returncode != 0:
            raise RuntimeError(
                f"yt-dlp 下载失败（exit={result.returncode}）：\n"
                f"{(result.stderr or result.stdout)[-2000:]}"
            )
        # 返回最匹配的文件（这里只返回目录，调用方自己再遍历找）
        return out_dir


def sys_executable() -> str:
    """PyInstaller 打包后优先用 sys.executable 同目录 python.exe；否则 sys.executable。"""
    import sys
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return exe  # 打包环境一般要求在支持目录安装 python/yt-dlp
    return exe


def crawl_latest(sec_uid: str = DEFAULT_SEC_UID, count: int = 10):
    return DouyinCrawler(sec_uid=sec_uid).list_latest_videos(count=count)


if __name__ == "__main__":
    # 独立调试：python -m src.crawler.douyin
    crawler = DouyinCrawler()
    crawler.ensure_login()
    vids = crawler.list_latest_videos(count=10)
    for v in vids:
        print(v.aweme_id, v.desc, v.web_url)
