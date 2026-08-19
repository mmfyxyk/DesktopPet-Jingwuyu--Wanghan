"""抖音首登引导 — 一次性脚本。

用途：
    第一次接入抖音爬虫时，需要先扫码登录一次（你自己的账号，账号密码永远
    不会写进本项目 / 也不会上传到 GitHub）。

工作方式：
    1) 用 support/Chrome/Application/chrome.exe 开启一个「独立用户资料目录」
       support/Chrome/Profile-Douyin/。这跟你本机的 Chrome 配置完全隔离。
    2) 自动跳抖音首页，页面右上角会出现「登录」按钮 / 二维码弹层。
       打开抖音 App → 右上角「≡」→「扫一扫」→ 扫屏幕上的码。
    3) 登录成功后，页面右上角会变成你的头像 + 昵称。
    4) 回到本脚本，按回车 Enter。程序会把 Cookie 保存成：
       - data/douyin_cookies.json   (requests/Selenium 注入用)
       - data/douyin_cookies.txt    (yt-dlp --cookies 用，Netscape 格式)
    5) 以后程序跑起来，只要这两个文件 + Profile-Douyin 目录还在，就
       不需要你再扫码了。Cookie 偶尔失效时再跑一次本脚本即可。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.crawler.douyin import DouyinCrawler  # noqa: E402


def main() -> int:
    crawler = DouyinCrawler()
    print("=" * 68)
    print("抖音首次扫码登录工具")
    print(f"  Chrome             : {crawler.chrome_exe}")
    print(f"  用户资料目录（独立）: {crawler.user_data_dir}")
    print(f"  Cookie(JSON)       : {crawler.cookie_file}")
    print(f"  Cookie(Netscape)   : {crawler.cookie_jar_netscape}")
    print("=" * 68)
    print()
    print("说明：")
    print("  • 接下来将弹出 Chrome 窗口，并自动打开抖音首页。")
    print("  • 用抖音手机 App 扫码登录（账号、短信验证码等方式都可）。")
    print("  • 登录成功后，页面右上角会显示你的头像/昵称，此时回到这个窗口。")
    print("  • 登录成功以后，回到本终端按回车键继续；程序会自动保存 Cookie 并退出浏览器。")
    print()
    input("按任意键启动浏览器（Ctrl+C 可取消）……")

    driver = crawler._open_browser()
    try:
        driver.get("https://www.douyin.com/")
        input("\n现在请在浏览器中完成登录。完成后回到这里按 Enter 保存 Cookie... ")
        crawler._dump_cookies(driver)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print("✅ Cookie 已保存：")
    print("   ", crawler.cookie_file)
    print("   ", crawler.cookie_jar_netscape)
    print("以后爬抖音就不用再登录了。如果以后爬不到数据 → 再跑一次这个脚本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
