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
        logger=None,
    ):
        self.sec_uid = self.normalize_sec_uid(sec_uid)
        self.headless = headless
        self.proxy = proxy
        # 日志回调：GUI 场景传 worker.log.emit，步骤信息自动同步到浮层
        self.logger = logger if callable(logger) else (lambda m: print(f"[抖音爬虫] {m}"))

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

        GUI 用这个做「退出登录」。
        - 强杀残留 chrome.exe/chromedriver.exe（避免 rmtree profile_dir 时被占用）
          （只杀携带 --user-data-dir=<本 crawler 专属 profile> 的进程；找不到就按父目录名兜底，
           不会影响用户自己平时用的桌面 Chrome）
        - profile_dir 删除后再额外清理一次 SingletonLock / lockfile / CrashpadMetrics 等残留锁文件
        """
        import shutil
        import glob
        import subprocess as _sp
        removed: list[str] = []
        locs = self.login_data_locations()

        # 0) 先尽力 kill 残留 Chrome 进程（便携版目录下的 chrome.exe，或者 --user-data-dir 指向我们 profile 的）
        profile_path = locs.get("chrome_profile_dir") or ""
        profile_norm = os.path.normpath(profile_path)
        if profile_path:
            try:
                import psutil  # 轻量 psutil 优先；没装就走 wmic 兜底
                for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
                    try:
                        pname = (proc.info.get("name") or "").lower()
                        if pname not in ("chrome.exe", "chromedriver.exe", "chrome", "chromedriver"):
                            continue
                        cmd = " ".join(proc.info.get("cmdline") or [])
                        if profile_norm.lower() in cmd.lower() or self.chrome_exe.lower() in cmd.lower():
                            proc.kill()
                            try:
                                proc.wait(timeout=5)
                            except Exception:
                                pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        continue
            except Exception:
                # 兜底：wmic 按可执行路径杀（便携版 support/Chrome/... 里的 chrome.exe，不碰 C:\Program Files 里的）
                try:
                    wmic_out = _sp.check_output(
                        ["wmic", "process", "where",
                         f"ExecutablePath='{self.chrome_exe}'", "get", "ProcessId"],
                        text=True, timeout=15,
                    )
                    for tok in wmic_out.split():
                        if tok.isdigit():
                            try:
                                _sp.run(["taskkill", "/F", "/PID", tok], timeout=10,
                                        capture_output=True, check=False)
                            except Exception:
                                pass
                except Exception:
                    pass
            # 小等一下，让 OS 释放文件句柄
            import time as _t
            _t.sleep(0.6)

        # 1) Profile 目录最占体积，用 shutil rmtree；失败就逐个锁文件重试
        d = locs["chrome_profile_dir"]
        if os.path.isdir(d):
            # 1.1 先把几个"最常见导致 rmtree 失败的锁文件"逐个尝试删（只读/系统属性都清）
            lock_glob_patterns = [
                os.path.join(d, "SingletonLock"),
                os.path.join(d, "SingletonSocket"),
                os.path.join(d, "SingletonCookie"),
                os.path.join(d, "lockfile"),
                os.path.join(d, "Default", "LOCK"),
                os.path.join(d, "Default", "LOCK-journal"),
                os.path.join(d, "GrShaderCache", "*"),
                os.path.join(d, "ShaderCache", "*"),
                os.path.join(d, "GPUCache", "*"),
                os.path.join(d, "Crashpad", "metrics*"),
                os.path.join(d, "*.lock"),
            ]
            for pat in lock_glob_patterns:
                for p in glob.glob(pat, recursive=False):
                    try:
                        if os.path.isdir(p):
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            os.chmod(p, 0o666)
                            os.remove(p)
                    except OSError:
                        pass
            try:
                shutil.rmtree(d)
                removed.append(f"profile_dir  {d}")
            except OSError:  # 真的被占用时就不强求
                pass
        # 2) json / netscape
        for key in ("cookies_json", "cookies_netscape"):
            f = locs[key]
            if os.path.isfile(f):
                try:
                    os.remove(f)
                    removed.append(f"{key:<17} {f}")
                except OSError:
                    pass
        return removed

    def force_refresh_cookies_from_profile(self) -> bool:
        """**yt-dlp 报 Fresh cookies / cookie 不一致** 时调用。
        走一次极简 Selenium：复用 profile_dir 打开首页（不做任何登录动作）→ 提取浏览器当前真实
        cookies → 重新写入 JSON + Netscape 两份。
        成功返回 True；任何原因失败返回 False（不会抛）。
        """
        driver = None
        try:
            if not (os.path.isdir(self.user_data_dir) or os.path.isfile(self.cookie_file)):
                return False
            driver = self._open_browser(foreground=False)
            driver.get("https://www.douyin.com/")
            import time as _t
            _t.sleep(3)
            self._dump_cookies(driver)
            return True
        except Exception:
            return False
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass


    # ------------------------------------------------------------------ tools

    def _build_options(self) -> Options:
        opts = Options()
        opts.binary_location = self.chrome_exe
        # 关键：user-data-dir 让 Chrome 记住登录态（Cookie、localStorage 全在里面）
        opts.add_argument(f"--user-data-dir={self.user_data_dir}")

        # ✨ 提速 1：不再等「所有图片/广告/瀑布流视频加载完」才算 goto 完成。
        # eager 让 DOMContentLoaded 一触发就返回，后台继续懒加载其他资源，
        # 配合我们后续 WebDriverWait 精确等"卡片/登录按钮"最稳。
        try:
            opts.page_load_strategy = "eager"
        except Exception:
            pass

        # 抖音对无痕识别很严 → 不要 --incognito
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument(f"--user-agent={USER_AGENT}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        # ✨ 提速 2：屏蔽 3P 埋点/广告域名（通过 DNS 0.0.0.0 黑掉，省 TCP+TLS 握手时间）
        opts.add_argument(
            "--host-resolver-rules="
            "MAP analytics*.snssdk.com 0.0.0.0,"
            "MAP mssdk*.snssdk.com 0.0.0.0,"
            "MAP xlog*.snssdk.com 0.0.0.0,"
            "MAP *.pstatp.com 0.0.0.0,"
            "MAP *.google-analytics.com 0.0.0.0,"
            "MAP *.googletagmanager.com 0.0.0.0,"
            "MAP *.doubleclick.net 0.0.0.0"
        )
        # 常见首启动干扰
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--no-first-run")
        opts.add_argument("--disable-sync")
        opts.add_argument("--disable-default-apps")

        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        # proxy 三态：None 跟随系统（不设任何命令行参数）；""=强制直连；URL=手动
        if self.proxy == "":
            opts.add_argument("--no-proxy-server")
        elif self.proxy:
            # 注意：Chrome --proxy-server=http://xxx 可以自动处理 http / https 流量
            # 但 socks5://... 必须写成 scheme://host:port 原样传
            opts.add_argument(f"--proxy-server={self.proxy}")
            opts.add_argument("--proxy-bypass-list=<-loopback>;127.0.0.1;localhost")
        return opts

    def _open_browser(self, *, foreground: bool = False) -> webdriver.Chrome:
        """打开便携版 Chrome。

        本版本额外做了 3 件事让抖音不再"加载半天没反应"：
          1) page_load_strategy=eager（不等所有图片/广告/媒体资源）
          2) host-resolver-rules 黑掉 3P 埋点/广告域名
          3) 注册 CDP 轻量请求拦截：对 Image/Media/Font 全部直接放行（不会阻塞页面），
             但后续在 goto 后会单独检测 captcha/风控。
        """
        if not os.path.isfile(self.chrome_exe) or not os.path.isfile(self.chromedriver_exe):
            raise DouyinLoginRequired(
                "缺少 support/Chrome/Application/chrome(.exe) 或 chromedriver.exe"
            )
        self.logger(f"启动 Chrome：exe={self.chrome_exe}，driver={self.chromedriver_exe}")
        self.logger(f"  用户资料目录={self.user_data_dir}")
        service = Service(self.chromedriver_exe)
        driver = webdriver.Chrome(service=service, options=self._build_options())
        self.logger("  Chrome 已启动，开始注入 webdriver 指纹隐藏脚本…")
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
        # 注册一个 Fetch 级别的"图像/媒体/字体全部放行"，避免我们 eager + 黑广告后仍有等待。
        # （老 chromedriver 可能不支持命令，静默忽略即可。）
        try:
            driver.execute_cdp_cmd(
                "Fetch.enable",
                {
                    "patterns": [
                        {"urlPattern": "*", "resourceType": "Image"},
                        {"urlPattern": "*", "resourceType": "Media"},
                        {"urlPattern": "*", "resourceType": "Font"},
                    ],
                    "handleAuthRequests": False,
                },
            )
        except Exception:
            pass

        if foreground:
            self.logger("  切前台最大化（登录/扫码场景）")
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
            # —— 不再 minimize_window()：你要看标签转圈圈、F12 看网络请求排错就必须能看到窗口
            self.logger("  后台普通窗口打开（不最小化，方便你观察标签页进度圈）")
            try:
                driver.set_window_position(40, 80)
                driver.set_window_size(1040, 720)
            except Exception:
                pass
        return driver

    # ------------------------------------------------------------------ login anti-spam

    @staticmethod
    def _detect_anti_spam_signals(driver) -> list[str]:
        """扫描页面是否命中**反爬 / 人机挑战**关键词或元素。

        返回非空 list[str] 时表示命中典型信号（文字点选 / 滑块 / 风控 iframe 等）。
        不会抛异常，任何时候调用都安全。
        """
        signals: list[str] = []
        try:
            cur_url = (driver.current_url or "").lower()
        except Exception:
            cur_url = ""
        if any(k in cur_url for k in (
            "/verify", "verify.snssdk", "verify.douyin", "challenge", "captcha", "security_check",
        )):
            signals.append(f"当前 URL 就是风控/验证页：{cur_url[:120]}")

        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text or ""
        except Exception:
            page_text = ""
        text_low = page_text.lower()
        keyword_hints = [
            ("文字点选验证（按顺序点击文字）",
             ("点击对应文字", "按顺序点击", "点选验证", "verification", "verify", "文字验证")),
            ("滑块验证码 / 拼图（向右拖动滑块完成拼图）",
             ("拖动滑块", "向右滑动", "滑块验证", "完成拼图", "滑动验证", "slide to verify")),
            ("通用人机挑战框（验证码）",
             ("人机验证", "安全验证", "请完成验证", "please complete the security check",
              "captcha", "are you a robot")),
            ("极验/行为验证（常见是点选 3/4 个字/图标）",
             ("geetest", "行为验证", "select the characters")),
        ]
        for label, kws in keyword_hints:
            if any(k in text_low for k in kws):
                signals.append(label)

        probe_css = [
            "iframe[src*='verify']", "iframe[src*='captcha']", "iframe[src*='challenge']",
            "iframe[id*='captcha']", "iframe[id*='verify']",
        ]
        found_iframes: list[str] = []
        for css in probe_css:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, css)
            except Exception:
                els = []
            for e in els:
                try:
                    src = e.get_attribute("src") or ""
                except Exception:
                    src = ""
                if src and src not in found_iframes:
                    found_iframes.append(src[:160])
        if found_iframes:
            signals.append("命中风控 iframe：" + "；".join(found_iframes[:3]))
        return signals

    def _emit_anti_spam_if_any(self, driver, *, stage: str) -> None:
        """统一封装：命中反爬就打醒目 log，不再出现「加载半天没反应，不知道发生了啥」。"""
        try:
            signals = self._detect_anti_spam_signals(driver)
        except Exception:
            return
        if not signals:
            return
        self.logger(
            f"⚠️  [抖音风控][阶段: {stage}] 检测到人机挑战信号：{'; '.join(signals)}\n"
            "   👉 请立刻切到 Chrome 窗口手动完成（点文字 / 拖滑块 / 过拼图）；\n"
            "   👉 如果弹窗迟迟不出，点一下页面上的「登录」按钮或刷新一次浏览器（F5）。\n"
            "   👉 反复命中且手动解不掉：大概率是代理/自动化指纹被识别，先切「强制直连」或换一个干净的代理再试。"
        )


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
            # —— 新加：检测抖音人机挑战（文字点选/滑块/iframe），一旦命中就立刻打醒目提示 ——
            self._emit_anti_spam_if_any(driver, stage="打开抖音首页(ensure_login)")

            already_logged_in = self._check_logged_in(driver)
            if already_logged_in:
                self._dump_cookies(driver)
                return

            # 首页有时候不会自己弹二维码（新版抖音会把入口藏在顶部登录按钮里）。
            # 主动尝试点击一下"登录"或「扫码登录」按钮 / 关掉协议弹窗。
            self._try_show_login_qr_or_panel(driver)
            # 弹窗被我们点出来之后，再扫一次风控（有的是"点登录按钮后才弹拼图/文字验证"）
            self._emit_anti_spam_if_any(driver, stage="主动弹登录面板后(ensure_login)")

            print(
                "[抖音爬虫] 请在弹出的 Chrome 窗口中用抖音 App 扫码登录。\n"
                f"[抖音爬虫] 登录成功后程序将在 {max_wait_sec}s 内自动检测并继续。"
            )

            # 等登录成功；每 3s 顺带扫一次风控（避免用户一直死等）
            t_max = max(3, int(max_wait_sec))
            _slept = 0
            while _slept < t_max:
                if self._check_logged_in(driver):
                    self._dump_cookies(driver)
                    return
                import time as _t
                _t.sleep(3)
                _slept += 3
                if _slept % 15 == 0:
                    self._emit_anti_spam_if_any(driver, stage=f"等待用户扫码中({_slept}s)")
            # 最后超时了再扫一次，告诉用户到底是哪卡住
            self._emit_anti_spam_if_any(driver, stage="ensure_login 等待超时")
            raise DouyinLoginRequired(f"{t_max}s 内未检测到登录成功。请重新发起登录。")
        finally:
            driver.quit()

    @staticmethod
    def _try_show_login_qr_or_panel(driver) -> None:
        """**主动让登录面板显形**。
        新版抖音常见 3 种"点登录按钮没反应"的情况，本 helper 一并处理：
          1) 有「同意用户协议 / 隐私政策」复选框 → 先勾上（抖音要求勾了按钮才能点）
          2) 右上角有「登录 / 立即登录」按钮 → 点一下（Selenium click；失败就用 JS dispatchEvent 兜底）
          3) 已弹出登录方式选择卡片（密码 / 验证码 / 扫码）→ 点「扫码登录」或带二维码图标的选项
        全部失败静默，不抛。上层仍靠 _check_logged_in 三态判定。
        """
        import time as _t

        # Step A：先把各种"遮挡/协议"的覆盖层尝试处理掉
        overlay_patterns = [
            # 同意协议复选框（新版：label / span 里带"已阅读"或"同意"，旁边 input[type=checkbox]）
            (By.XPATH, "//label[contains(normalize-space(.), '已阅读')]//input[@type='checkbox']"),
            (By.XPATH, "//label[contains(normalize-space(.), '同意')]//input[@type='checkbox']"),
            # 「同意 / 接受 / 确认」按钮：常见弹底部
            (By.XPATH, "//button[normalize-space()='同意并继续']"),
            (By.XPATH, "//button[normalize-space()='同意并登录']"),
            (By.XPATH, "//button[normalize-space()='同意']"),
            (By.XPATH, "//div[@role='button'][normalize-space()='同意']"),
            # "x" 小关闭按钮：常见遮罩右上角
            (By.CSS_SELECTOR, ".dy-account-close"),
            (By.XPATH, "//div[contains(@class,'close') and contains(@class,'login')]"),
        ]
        for by, sel in overlay_patterns:
            try:
                els = WebDriverWait(driver, 3).until(
                    EC.presence_of_all_elements_located((by, sel))
                )
            except Exception:
                continue
            for e in els:
                try:
                    if not e.is_displayed():
                        continue
                    tag = (e.tag_name or "").lower()
                    if tag == "input" and (e.get_attribute("type") or "").lower() == "checkbox":
                        if not e.is_selected():
                            try:
                                e.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", e)
                    else:
                        try:
                            e.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", e)
                    _t.sleep(0.5)
                except Exception:
                    continue

        # Step B：找登录按钮并点一下（先普通 click；失败用 JS 兜底）
        login_btns_selectors = [
            "//button[normalize-space(text())='登录']",
            "//div[@role='button'][normalize-space(.)='登录']",
            "//span[normalize-space(.)='登录']",
            "//a[normalize-space(.)='登录']",
            "//button[contains(., '立即登录')]",
        ]
        clicked_login = False
        for xp in login_btns_selectors:
            try:
                candidates = driver.find_elements(By.XPATH, xp)
            except Exception:
                continue
            for c in candidates:
                try:
                    if not c.is_displayed():
                        continue
                    try:
                        c.click()
                    except Exception:
                        driver.execute_script(
                            "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));",
                            c,
                        )
                    clicked_login = True
                    _t.sleep(0.8)
                    break
                except Exception:
                    continue
            if clicked_login:
                break

        # 给页面 1s 弹出登录卡片，再尝试切"扫码登录"
        _t.sleep(1.0)
        qr_selectors = [
            "//div[contains(@role,'tab') and contains(normalize-space(.), '扫码')]",
            "//span[contains(normalize-space(.), '扫码登录')]",
            "//*[name()='svg' and contains(normalize-space(.), '二维码')]/ancestor::button | //button[contains(normalize-space(.), '二维码')]",
            "//div[contains(@class, 'qrcode') or contains(@class, 'qr-code') or contains(@class, 'QRCode')]",
        ]
        for xp in qr_selectors:
            try:
                els = driver.find_elements(By.XPATH, xp)
            except Exception:
                continue
            for e in els:
                try:
                    if not e.is_displayed():
                        continue
                    try:
                        e.click()
                    except Exception:
                        driver.execute_script(
                            "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));",
                            e,
                        )
                    _t.sleep(0.8)
                    return
                except Exception:
                    continue

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
        #    yt-dlp extractor 对抖音 cookie（sessionid_ss / odin_tt / ttwid / msToken /
        #    bd_ticket_guard_client_data 等）很挑剔；按下面规范写：
        #      - 首行：# Netscape HTTP Cookie File
        #      - #HttpOnly_<domain> 前缀：仅当 cookie.httpOnly=True 且 yt-dlp 需要时
        #      - domain 字段：带点的就是"主子域通吃"（.douyin.com / .amemv.com / .iesdouyin.com）
        #      - 少字段的（没 domain/path/value）过滤掉
        jar_path = self.cookie_jar_netscape
        # 用 MozillaCookieJar 存一份 + 确保头行；然后把所有记录里的 cookie 字段都
        # 带 secure/httpOnly 补齐兼容
        jar = MozillaCookieJar(jar_path)
        for c in cookies:
            if not c.get("domain") or not c.get("path"):
                continue
            # yt-dlp 需要抖音 cookie 的值非空；空值基本无用
            if c.get("value") in (None, ""):
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
                rest={"HttpOnly": "true" if c.get("httpOnly") else ""},
                rfc2109=False,
            ))
        jar.save(ignore_discard=True, ignore_expires=True)
        # jar.save() 自带的是 "# HTTP Cookie File"，yt-dlp extractor 更喜欢
        # "# Netscape HTTP Cookie File"；顺手把文件首行替换，同时确保非空
        try:
            with open(jar_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            text = text.replace("# HTTP Cookie File", "# Netscape HTTP Cookie File", 1)
            if not text.startswith("# Netscape HTTP Cookie File"):
                text = "# Netscape HTTP Cookie File\n" + text
            with open(jar_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

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
        # proxy 三态：None→跟随系统（requests 默认行为）；""→强制直连；URL→手动
        if self.proxy is None:
            pass
        elif self.proxy == "":
            s.trust_env = False
            s.proxies.clear()
            s.proxies.update({"http": "", "https": ""})
        else:
            s.proxies.update({"http": self.proxy, "https": self.proxy})
        return s

    # ------------------------------------------------------------------ list videos

    def list_latest_videos(self, count: int = 10) -> list[DouyinVideo]:
        """爬取 UP 主主页最新作品。带极细步骤日志 + 失败时页面快照，方便你秒定位卡在哪。

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

        self.logger(f"sec_uid={self.sec_uid}，目标作品数={count}")
        # 爬取场景：已经登录过 → 不最小化，留个可观察的窗口
        driver = self._open_browser(foreground=False)
        try:
            home_url = f"https://www.douyin.com/user/{self.sec_uid}"
            self.logger(f"导航到个人主页：{home_url}")
            driver.get(home_url)

            # ✨ 抖音反爬："打开半天不出来"很多时候是先弹文字/拼图验证，用户没看见我们就在等死等。
            self._emit_anti_spam_if_any(driver, stage="打开UP主页(list_latest_videos)")

            # 0) 等待首屏文档 ready（最长 20s），避免 "标签一直转圈"时我们就急着去读空 DOM
            self.logger("  等待首屏 document.readyState=complete（≤ 20s）…")
            try:
                WebDriverWait(driver, 20).until(
                    lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
                )
                self.logger("  首屏 document complete，等待 SPA 作品区渲染…")
            except Exception as e:
                self.logger(f"  首屏 20s 超时 / 页面脚本异常：{type(e).__name__}: {e}")
                self._emit_anti_spam_if_any(driver, stage="首屏ready超时")

            # 1) 页面里出现"非法用户/不存在" → sec_uid 错了或账号被限制，立刻抛
            self._detect_fatal_page(driver)
            self.logger("  没有命中「非法用户」等坏页关键字，继续…")

            # 2) 检查当前是不是"被要求登录"状态（有些私密用户/风控会在主页上强制出登录弹窗）
            login_ok = self._check_logged_in(driver)
            self.logger(f"  登录态检测：{'✅ 已登录' if login_ok else '❌ 未登录或页面不完整'}")
            if not login_ok:
                # 再扫一次风控（很多时候"未登录"只是被验证码挡住了）
                self._emit_anti_spam_if_any(driver, stage="登录态判定为False(cookie可能还行但被验证码挡住)")
                # 把当前 URL/标题/页面关键字打到日志，帮你判断是 cookie 过期还是风控验证码
                url_now = driver.current_url or ""
                title = driver.title or ""
                src_snippet = (driver.page_source or "")[:400]
                self.logger(f"  —— 当前快照 URL：{url_now}")
                self.logger(f"  —— 当前快照 TITLE：{title}")
                self.logger(f"  —— 页面源码片段（前 400 字）：{src_snippet!r}")
                raise DouyinLoginRequired(
                    "抖音登录态已过期（有 Cookie 文件但页面判定未登录）。\n"
                    "请使用菜单：拓展功能 → 抖音 → 清除登录数据（退出登录），然后再做一次 登录/重新登录（扫码）。\n"
                    "若上方日志里看到「⚠️ [抖音风控] … 安全验证 / 验证码 / 滑块」等字样，属于抖音网页版风控，在你刚打开的 Chrome 里手动过一次验证，然后重新爬取即可。"
                )

            # 3) 等作品卡片。抖音前端新版本经常换 class，选择器 a[href*="/video/"] 是最稳的兜底
            self.logger("  等待作品 a[href*=\"/video/\"] 卡片渲染（≤ 20s，等到即提前继续）…")
            waited_ok = False
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/video/"]'))
                )
                waited_ok = True
            except Exception as e:
                self.logger(f"  20s 没等到作品卡片：{type(e).__name__}（继续尝试读取当前页面里已有的 <a>，看是否命中）")
                self._emit_anti_spam_if_any(driver, stage="等待作品卡片超时(可能被验证码挡住)")

            # 3.5) 如果作品区还是空，可能是新版 SPA 还没 XHR 回数据，再给一次轻滚动触发懒加载
            anchors0 = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
            self.logger(f"  当前能查到的作品 a 数量：{len(anchors0)} （waited_ok={waited_ok}）")
            if len(anchors0) == 0:
                self.logger("  作品区还是空，尝试滚动一下触发懒加载…")
                try:
                    driver.execute_script(
                        "window.scrollTo({top: Math.max(300, document.body.scrollHeight * 0.3), behavior: 'instant'});"
                    )
                    import time as _t
                    _t.sleep(1.5)
                except Exception as e:
                    self.logger(f"  滚动失败：{type(e).__name__}: {e}")

            # 4) 从页面里拿多少算多少
            hrefs: list[str] = []
            # 4.1) Selenium 选择器兜底（CSS 精确匹配 <a href>）
            for a in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]'):
                try:
                    href = a.get_attribute("href") or ""
                except Exception:
                    continue
                if href and "/video/" in href and href not in hrefs:
                    hrefs.append(href)
            self.logger(f"  [选择器 1/2] a[href*=\"/video/\"] 拿到：{len(hrefs)} 条")

            # 4.2) JS 兜底：直接在浏览器里遍历所有 <a> 的完整 href（含绝对化后的），再正则命中 /video/19 位数字
            #    这个兜底专门解决「用户肉眼看到作品全显示，但 Selenium get_attribute 取不到」的新版 DOM 情况
            if len(hrefs) < count:
                try:
                    js = r"""
                    const set = new Set();
                    const re = /\/video\/(\d{17,21})/;   // 19 位 aweme_id，上下兼容 2 位
                    document.querySelectorAll('a').forEach(a => {
                      const h = (a && (a.href || a.getAttribute && a.getAttribute('href')) || '').toString();
                      if (re.test(h)) set.add(h.split('#')[0].split('?')[0]);
                    });
                    // 兜底再扫一遍所有元素的 onclick / data-href / data-src，防止 URL 放属性里
                    document.querySelectorAll('*').forEach(el => {
                      for (const attr of ['data-href', 'data-src', 'data-to', 'to', 'href']) {
                        const v = el.getAttribute && el.getAttribute(attr);
                        if (typeof v === 'string' && re.test(v)) set.add(v.split('#')[0].split('?')[0]);
                      }
                    });
                    return Array.from(set);
                    """
                    js_hrefs = driver.execute_script(js) or []
                    added = 0
                    for h in js_hrefs:
                        if isinstance(h, str) and "/video/" in h and h not in hrefs:
                            # normalize 一下相对路径
                            if h.startswith("/video/"):
                                h = "https://www.douyin.com" + h
                            hrefs.append(h)
                            added += 1
                    self.logger(f"  [选择器 2/2] JS 遍历所有 a + 属性扫到新增：{added} 条（累计 {len(hrefs)} 条）")
                except Exception as e:
                    self.logger(f"  [选择器 2/2] JS 兜底失败（不致命，继续按 Selenium 结果）：{type(e).__name__}: {e}")

            self.logger(f"  最终解析到作品链接数：{len(hrefs)}")

            results: list[DouyinVideo] = []
            for href in hrefs[:count]:
                aweme_id = self._aweme_id_from_url(href)
                if not aweme_id:
                    continue
                try:
                    # 新版 DOM 里 <a> 本身往往没有 text，取其父节点的文本
                    desc = ""
                    try:
                        desc = (a.text or "").strip()
                        if not desc:
                            parent = a.find_element(By.XPATH, "..")
                            desc = (parent.text or "").strip()
                    except Exception:
                        pass
                    if not desc:
                        desc = aweme_id
                    # 限制长度，避免 UI 上一长条
                    if len(desc) > 60:
                        desc = desc[:58] + "…"
                except Exception:
                    desc = aweme_id
                results.append(DouyinVideo(
                    aweme_id=aweme_id,
                    web_url=href,
                    desc=desc,
                ))
            self.logger(f"  解析后保留的作品条目：{len(results)}")

            # 刷新一次 cookie（sessionid 可能被刷新）
            try:
                self.logger("  刷新 Cookie（JSON + Netscape）…")
                self._dump_cookies(driver)
                self.logger("  Cookie 刷新完成")
            except Exception as e:
                self.logger(f"  刷新 Cookie 失败（不影响本次结果）：{type(e).__name__}: {e}")

            if results:
                top_desc = results[0].desc
                self.logger(f"  返回 {len(results)} 条，最新一条：{top_desc}  {results[0].web_url}")
                return results

            # —— 还是 0 条 → 给你页面快照，方便排错 ——
            url_now = driver.current_url or ""
            title = driver.title or ""
            src = driver.page_source or ""
            self.logger("  ⚠️ 0 条作品，快照供排错：")
            self.logger(f"    URL：{url_now}")
            self.logger(f"    TITLE：{title}")
            self.logger(f"    页面源码包含 /video/ 吗：{'/video/' in src}")
            self.logger(f"    页面源码包含 作品 这两个字吗：{'作品' in src}")
            self.logger(f"    页面源码前 600 字：{src[:600]!r}")
        finally:
            self.logger("  关闭 Chrome…")
            try:
                driver.quit()
                self.logger("  Chrome 已关闭")
            except Exception as e:
                self.logger(f"  Chrome 关闭时异常：{type(e).__name__}: {e}")

        raise DouyinLoginRequired(
            "在已登录的 Chrome 里没解析到作品列表（0 条）。\n"
            "常见原因（看上面的快照日志判断）：\n"
            "  1) sec_uid 不对 / 账号被限制（私密 / 风控）。\n"
            "  2) 登录态过期，需要重新扫码。\n"
            "  3) 抖音改版，a[href*=\"/video/\"] 选择器没命中 —— 把上面快照贴出来即可修。\n"
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

        **临时/成品目录规则（跟 B 站保持一致）：**
          - 临时文件（yt-dlp 的 .ytdl/.part/分片/ffmpeg 合并前的音视频）统一落在
            data/tmp/douyin/<aweme_id>/…（不是 output 目录）。
          - 成功：yt-dlp 先把成品写在上面临时目录 → 原子 move 到 output/douyin/ → 然后
            clear_tmp_dir(tmp_dir) 清掉残留。
          - 失败：若错误特征是 cookie 类（Fresh cookies / HTTP 403 / Signature …），
            自动调用 `force_refresh_cookies_from_profile()` 用 profile 重新抓一遍真实
            cookies 重写 douyin_cookies.txt，再 retry 1 次；retry 仍失败才保留 tmp 现场。
        """
        import shutil as _shutil
        from ..resource_manager import get_tmp_path, clear_tmp_dir

        final_out_dir = out_dir or get_output_path("douyin")
        Path(final_out_dir).mkdir(parents=True, exist_ok=True)

        # 任务级临时目录：绝对路径 aweme_id 做子目录，路径唯一，成功后能精准删除不误删
        tmp_dir = get_tmp_path("douyin", video.aweme_id or f"task_{int(time.time()*1000)}")
        self.logger(f"临时目录（yt-dlp 落中间文件）：{tmp_dir}")
        self.logger(f"成品目录：{final_out_dir}")

        before_tmp: set[str] = set(os.listdir(tmp_dir)) if os.path.isdir(tmp_dir) else set()

        # —— 一次 yt-dlp 执行封装；返回 (rc, 累积的日志行首端, 临时目录新增文件) ——
        def _run_once(attempt_tag: str):
            cmd = [
                sys_executable(),
                "-m", "yt_dlp",
                "--no-warnings",
                "--cookies", self.cookie_jar_netscape,
                "--no-check-certificate",
                "-o", os.path.join(tmp_dir, "%(title).80s [%(id)s].%(ext)s"),
            ]
            if self.proxy is not None:
                cmd += ["--proxy", self.proxy or ""]
            cmd.append(video.web_url)

            # 只在第一次 attempt 打印命令，避免 retry 重复
            if attempt_tag == "1st":
                self.logger(
                    f"yt-dlp 命令行（已脱敏 cookies）：{' '.join(cmd[:-1])} <URL>"
                )
            self.logger(
                f"⏳ [{attempt_tag}] yt-dlp 下载 + ffmpeg 合并，进度按行实时回显（不要急）…"
            )

            popen_kwargs: dict = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            }
            if os.name == "nt":
                try:
                    popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
                except Exception:
                    CREATE_NO_WINDOW = 0x08000000
                    popen_kwargs["creationflags"] = CREATE_NO_WINDOW

            proc: Optional[subprocess.Popen] = None
            collected_errors: list[str] = []
            try:
                proc = subprocess.Popen(cmd, **popen_kwargs)
                assert proc.stdout is not None
                for raw in proc.stdout:
                    line = (raw or "").rstrip()
                    if not line:
                        continue
                    line_l = line.replace("\r", " | ").strip()
                    if len(line_l) > 220:
                        line_l = line_l[:217] + "…"
                    # error / warning 行单独摘出来，后续用来判断"要不要 refresh cookie + retry"
                    low = line_l.lower()
                    if any(k in low for k in (
                        "error:", "fresh cookies", "http 403", "signature", "unable to extract",
                        "cookie", "did not pass", "captcha",
                    )):
                        collected_errors.append(line_l)
                    if any(k in line_l for k in ("[download]", "[ffmpeg]", "[ExtractAudio]", "[Merger]", "[info]")):
                        self.logger("  " + line_l)
                    else:
                        self.logger("  yt-dlp：" + line_l)
                try:
                    proc.wait(timeout=15 * 60)
                except subprocess.TimeoutExpired:
                    self.logger(
                        f"⚠️  [{attempt_tag}] yt-dlp 超过 15 分钟仍未退出，强制 kill…"
                        "（临时目录会保留，方便你排查）"
                    )
                    proc.kill()
                    try:
                        proc.wait(timeout=30)
                    except Exception:
                        pass
            except FileNotFoundError as e:
                raise RuntimeError(f"找不到 python / yt-dlp，先 pip install yt-dlp：{e}")
            except Exception as e:
                if proc is not None and proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=15)
                    except Exception:
                        pass
                raise RuntimeError(f"yt-dlp 执行异常：{type(e).__name__}: {e}")
            rc = proc.returncode if proc is not None else 1
            after = set(os.listdir(tmp_dir)) if os.path.isdir(tmp_dir) else set()
            new_files = sorted(after - before_tmp)
            return rc, collected_errors, new_files

        rc, errs_1st, new_files_1st = _run_once("1st")

        # 第一次失败 + 特征像 cookie 类问题 → 自动 refresh 一下 Netscape cookies 再试一次
        def _looks_cookie_error(errs: list[str], rc: int) -> bool:
            if rc == 0:
                return False
            merged = "\n".join(errs).lower()
            return any(k in merged for k in (
                "fresh cookies",
                "http 403",
                "signature",
                "unable to extract",
                "please login",
                "cookie",
                "did not pass",
                "captcha",
            ))

        errs_all = errs_1st[:]
        new_files = new_files_1st
        if rc != 0 and _looks_cookie_error(errs_1st, rc):
            self.logger(
                "🔁  首跑失败，错误特征像 cookie 类 / 签名类问题；"
                "现在尝试打开抖音首页从 profile 里刷新一遍 cookies.txt（不会让你重新扫码）然后自动 retry 1 次…"
            )
            refreshed = self.force_refresh_cookies_from_profile()
            self.logger(f"  cookies 刷新结果：{'成功' if refreshed else '失败（继续尝试 retry）'}")
            # 清掉首次 attempt 的半成品，避免"临时目录里 dup 了分不清"
            try:
                if os.path.isdir(tmp_dir):
                    for f in new_files_1st:
                        p = os.path.join(tmp_dir, f)
                        if os.path.isfile(p):
                            try:
                                os.remove(p)
                            except OSError:
                                pass
            except Exception:
                pass
            before_tmp = set(os.listdir(tmp_dir)) if os.path.isdir(tmp_dir) else set()
            rc2, errs_2nd, new_files_2nd = _run_once("2nd(retry)")
            errs_all = errs_1st + errs_2nd
            new_files = new_files_2nd
            rc = rc2

        def _kind(name: str) -> str:
            n = name.lower()
            if n.endswith((".ytdl", ".part", ".temp", ".tmp")) or ".frag" in n:
                return "半成品"
            if n.endswith((".mp4", ".webm", ".mkv", ".mp3", ".wav", ".m4a")):
                return "成品"
            return "其它"

        # 找一下临时目录里是否有「成品」视频（yt-dlp 成功后才会把 .part 去掉）
        candidate: Optional[str] = None
        for f in new_files:
            if _kind(f) == "成品":
                cand = os.path.join(tmp_dir, f)
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    candidate = cand
                    break

        if rc != 0 or candidate is None:
            self.logger(f"❌ yt-dlp 返回码：{rc}（非 0 = 失败）")
            self.logger(f"  临时目录 {tmp_dir} 中新增文件（失败就保留现场，不移动到 output、也不清理）：")
            if not new_files:
                self.logger(
                    "    （空，yt-dlp 在开始下载之前就失败了。典型原因：\n"
                    "      · douyin_cookies.txt 过期 / 缺 sessionid_ss；先 pip install -U yt-dlp 再「清除登录数据 → 重新登录」\n"
                    "      · 你设置的代理网络不通，yt-dlp 打 --proxy 之后连不上；可切到直连或换一个代理再试）"
                )
            else:
                for f in new_files:
                    try:
                        size_kb = int(os.path.getsize(os.path.join(tmp_dir, f)) // 1024)
                    except Exception:
                        size_kb = -1
                    self.logger(f"    · [{_kind(f)}] {f}  ({size_kb} KB)")
            # 额外把收集到的 error 行里"最后一条最具代表性的"贴在结尾，省得你自己往上翻几百行
            tail_err = errs_all[-1] if errs_all else ""
            raise RuntimeError(
                f"yt-dlp 下载失败（exit={rc}）。\n"
                f"看上面的「yt-dlp：…」逐行日志找最后一条错误；\n"
                f"如果含 'Fresh cookies' / 'Signature' / 'Unable to extract' / 'HTTP 403'，通常是：\n"
                "  (1) yt-dlp 版本旧 → .venv\\Scripts\\pip.exe install -U yt-dlp  \n"
                "  (2) cookie 里缺 sessionid_ss/odin_tt/ttwid → 菜单：清除登录数据 → 重新扫码登录  \n"
                "  (3) 抖音又换了新版签名，yt-dlp 新版通常 1~3 天内就会跟进，升级 yt-dlp 就能过。\n"
                f"（程序已自动尝试 1 次「从 profile 刷新 cookies.txt 后 retry」）\n"
                f"最近一次错误：{tail_err}\n"
                f"临时文件保留在：{tmp_dir}"
            )

        # 成功：把成品 move 到 output/douyin/（同盘原子 move；跨盘就 copy+delete）
        self.logger(f"✅ yt-dlp 完成，exit={rc}，找到临时成品：{candidate}")
        dst_path = os.path.join(final_out_dir, os.path.basename(candidate))
        # 避免冲突：同名文件加 _dup1 _dup2 …
        base, ext = os.path.splitext(dst_path)
        i = 1
        final = dst_path
        while os.path.exists(final):
            final = f"{base}_dup{i}{ext}"
            i += 1
        try:
            # 同盘优先 rename（原子）
            os.replace(candidate, final)
        except OSError:
            # 跨盘（比如 exe 装在 C:，tmp 和 output 实际同盘但有时候受重解析点影响）
            _shutil.move(candidate, final)
        self.logger(f"  成品已移动到：{final}")

        # 成功 → 强制清理临时目录（哪怕里面还残留 .ytdl / .part / 未被合并的分片，都直接删）
        ok_clear = clear_tmp_dir(tmp_dir)
        self.logger(f"  临时目录清理（成功后清理）：{'✅ 已清空' if ok_clear else '⚠️ 目录里还有文件锁/占用，稍后去 data/tmp/douyin/ 手动删即可'}")

        # 返回最终成品所在目录（UI 方通过 find_first_file_in_dir 找最新文件高亮）
        return final_out_dir


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
