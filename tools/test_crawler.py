"""爬虫链路诊断脚本（独立运行，不依赖主窗口）

分 3 步输出证据；失败时能明确看到卡在哪一环。
"""
from __future__ import annotations

import os
import sys
import time
import traceback

# 项目根加进 sys.path，方便直接 `python tools/test_crawler.py`
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.resource_manager import get_support_path  # noqa: E402
from src.crawler.bilibili import (  # noqa: E402
    DEFAULT_MID,
    DEFAULT_SPACE_URL,
    LATEST_VIDEO_XPATHS,
    SELENIUM_WAIT_TIMEOUT,
    USER_AGENT,
    BilibiliCrawler,
    CrawlerError,
)
from selenium import webdriver  # noqa: E402
from selenium.webdriver.chrome.options import Options  # noqa: E402
from selenium.webdriver.chrome.service import Service  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402


def banner(n: int, text: str) -> None:
    print("\n" + "=" * 68)
    print(f"[Step {n}] {text}")
    print("=" * 68)


def step1_tools_check() -> bool:
    banner(1, "工具链存在性检查")
    paths = {
        "Chrome 浏览器": get_support_path("Chrome", "Application", "chrome.exe"),
        "chromedriver": get_support_path("Chrome", "Application", "chromedriver.exe"),
        "ffmpeg": get_support_path("ffmpeg", "bin", "ffmpeg.exe"),
    }
    all_ok = True
    for name, p in paths.items():
        ok = os.path.isfile(p)
        print(f"  [{'OK' if ok else '!!'}] {name:<15} -> {p}")
        if not ok:
            all_ok = False
    if not all_ok:
        print("\n缺失上述任一文件时 Selenium / ffmpeg 步骤将无法通过。")
    return all_ok


def step2_space_page_probe() -> str | None:
    banner(2, "Selenium 打开 UP 主空间，诊断页面状态")
    chrome_exe = get_support_path("Chrome", "Application", "chrome.exe")
    driver_exe = get_support_path("Chrome", "Application", "chromedriver.exe")
    if not os.path.isfile(chrome_exe) or not os.path.isfile(driver_exe):
        print("  [跳过] Chrome/chromedriver 缺失，Selenium 无法启动。")
        return None

    chrome_options = Options()
    chrome_options.binary_location = chrome_exe
    service = Service(driver_exe)
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--incognito")
    chrome_options.add_argument(f"--user-agent={USER_AGENT}")

    web = webdriver.Chrome(service=service, options=chrome_options)
    try:
        web.minimize_window()
        print(f"  GET {DEFAULT_SPACE_URL}")
        web.get(DEFAULT_SPACE_URL)

        print(f"  等待 {SELENIUM_WAIT_TIMEOUT}s 让页面加载（等 #app 或 body）……")
        try:
            WebDriverWait(web, SELENIUM_WAIT_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except Exception as e:
            print(f"  等待 body 超时: {e}")

        # 真实证据：标题、URL、body 前 300 字符
        print(f"  page_title     : {web.title!r}")
        print(f"  current_url    : {web.current_url}")
        print(f"  page_src_len   : {len(web.page_source)} 字符")
        print(f"  body[:200]     : {web.find_element(By.TAG_NAME, 'body').text[:200]!r}")

        # 尝试找 UP 主名字
        try:
            name_elem = web.find_element(By.ID, "h-name")
            print(f"  h-name(UP主名) : {name_elem.text!r}")
        except Exception:
            print("  h-name(UP主名) : 未找到 #h-name，空间页可能未完成渲染或改版")

        # 依次尝试多个 XPATH（和真正爬虫里的兜底逻辑一致）
        print(f"  依次尝试 {len(LATEST_VIDEO_XPATHS)} 条 XPATH 找最新视频卡片…")
        href: str | None = None
        for idx, xpath in enumerate(LATEST_VIDEO_XPATHS, 1):
            try:
                el = WebDriverWait(web, 3).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                found = el.get_attribute("href")
                if found and "/video/" in found:
                    href = found
                    print(f"  XPATH #{idx} 命中: {xpath}")
                    print(f"  最新视频 a.href : {href}")
                    break
            except Exception:
                print(f"  XPATH #{idx} 未命中: {xpath}")
        if href is None:
            print("  !! 所有 XPATH 都没找到。")
            print("  退而求其次，扫描页面上所有带 /video/ 的链接：")
            all_links = web.find_elements(By.XPATH, "//a[@href]")
            candidates = []
            for a in all_links:
                link = (a.get_attribute("href") or "").strip()
                if "/video/" in link and link.startswith("http"):
                    candidates.append(link)
            unique = list(dict.fromkeys(candidates))
            print(f"  找到带 /video/ 的链接 {len(unique)} 条（前 10 条）：")
            for i, h in enumerate(unique[:10], 1):
                print(f"     {i:>2}. {h}")
        return href
    finally:
        try:
            web.quit()
        except Exception:
            pass


def step3_full_run() -> None:
    banner(3, "完整 crawl_latest_video() 一次")
    try:
        from src.crawler import crawl_latest_video
        info = crawl_latest_video()
        print()
        print("  ✅ 爬取成功")
        print(f"    标题    : {info.title}")
        print(f"    页面    : {info.page_url}")
        print(f"    音视频长度 audio/video url (前100):")
        print(f"      {info.audio_url[:100]}...")
        print(f"      {info.video_url[:100]}...")
        print(f"    输出文件: {info.output_path}")
        if os.path.isfile(info.output_path):
            size_kb = os.path.getsize(info.output_path) / 1024
            print(f"    文件大小: {size_kb:.1f} KB")
        else:
            print("    !! output 文件不存在（ffmpeg 可能没写）")
    except CrawlerError as e:
        print("  ❌ CrawlerError:", e)
    except Exception as e:
        print("  ❌ 未预期异常:", type(e).__name__, e)
        traceback.print_exc()


def main() -> int:
    print("B 站最新视频爬虫链路诊断")
    print(f"Python : {sys.version}")
    print(f"CWD    : {os.getcwd()}")
    print(f"ROOT   : {ROOT}")

    step1_tools_check()
    step2_space_page_probe()
    step3_full_run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
