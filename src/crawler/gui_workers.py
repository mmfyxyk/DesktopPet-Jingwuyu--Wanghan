"""抖音功能的 GUI 线程封装（QThread），不依赖终端。

提供两个 Worker：
- DouyinLoginWorker：在后台线程打开一个浏览器窗口引导用户扫码登录；
  通过 QMessageBox + log 信号把提示和结果回到 UI 线程。
- DouyinCrawlWorker：登录态正常时，抓取 UP 主最新作品 + 用 yt-dlp 下载；
  如果没登录 → failed 信号返回 DouyinLoginRequired，UI 层可提示用户先做登录。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QThread, Signal

from .bilibili import CrawlerError  # 复用同一个爬虫异常类型，UI 只认一种即可
from .douyin import (
    DEFAULT_SEC_UID,
    DouyinCrawler,
    DouyinLoginRequired,
    DouyinVideo,
)
from ..download_history import (
    DownloadRecord,
    forget_broken_entries,
    key_for_douyin,
    lookup as history_lookup,
    record as history_record,
)


class DouyinLoginWorker(QThread):
    """引导一次扫码登录，完成后保存 cookie。

    信号：
        finished_ok(str)  登录成功。参数 = 触发方式:
                            "auto"   = 用户在 Chrome 里登录后被我们的 1s 轮询自动检测到
                            "manual" = 用户在扫码确认对话框里点「确认登录完成」
                            "already"= 打开浏览器时就已经是登录态（无需扫码）
        failed(str)       登录失败
        log(str)          日志（打印到 Terminal + 同步任务浮层文案）
        user_action_required(str)   需要用户扫码时触发。UI 弹一个非阻塞的"扫码引导对话框"
                                     （对话框本身只是告知 + 提供"我已完成"按钮；不依赖对话框关闭
                                      也能自动检测登录成功）
    """

    finished_ok = Signal(str)     # 参数见上文
    failed = Signal(str)
    log = Signal(str)
    user_action_required = Signal(str)   # 参数：提示文案

    def __init__(
        self,
        headless: bool = False,
        proxy: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._headless = headless
        self._proxy = proxy
        self._allow = False

    def allow_proceed(self) -> None:
        """UI 侧在用户点击对话框「确认登录完成」后调用。"""
        self._allow = True

    def run(self) -> None:
        driver = None
        # —— 登录成功的触发方式：manual / auto / already（失败时保持 None）——
        trigger: str | None = None
        try:
            import time as _t
            crawler = DouyinCrawler(headless=self._headless, proxy=self._proxy, logger=self.log.emit)
            self.log.emit("正在启动浏览器（抖音专用用户资料目录）…")

            driver = crawler._open_browser(foreground=True)
            driver.get("https://www.douyin.com/")

            try:
                crawler._detect_fatal_page(driver)
            except DouyinLoginRequired as e:
                self.failed.emit(str(e))
                return

            # —— 辅助函数：升级判定 ——
            #   若当前命中宽松 True，最多再给 10 秒看能不能升级到强 True；
            #   能则返回 True，不能返回 False（继续等用户扫码/过验证）
            def _upgrade_to_strong() -> bool:
                for _ in range(10):
                    try:
                        if crawler._check_logged_in(driver, strong=True):
                            return True
                    except Exception:
                        pass
                    _t.sleep(1)
                return False

            # 路径 1：打开时就已登录（必须 strong=True 才承认；否则视为"残留过期cookie"，继续进入扫码流程）
            if crawler._check_logged_in(driver, strong=True):
                crawler._dump_cookies(driver)
                self.log.emit("当前已处于登录态，已直接保存 Cookie。")
                self.finished_ok.emit("already")
                return
            # 宽松命中但强命中失败 → 提示用户：profile里有cookie但实际上没真正登录，让用户重新扫码
            if crawler._check_logged_in(driver, strong=False):
                self.log.emit(
                    "检测到 Profile 里存在 Cookie 但 UI 未显示个人区域（头像/消息），"
                    "可能是登录态已过期或浏览器需要刷新。将继续引导你重新扫码登录。"
                )
                # 尝试主动刷新一下（有时刷新后就显示"未登录"按钮，便于用户直接扫）
                try:
                    driver.refresh()
                    _t.sleep(2.0)
                except Exception:
                    pass

            self.log.emit("页面打开成功，现在尝试自动让二维码面板出来（若你已经能看到二维码/登录弹窗可忽略本段）…")
            try:
                crawler._try_show_login_qr_or_panel(driver)
            except Exception as e:
                self.log.emit(f"（非致命）尝试自动弹出登录面板失败：{type(e).__name__}: {e}")

            self.log.emit("浏览器已打开并跳转到抖音首页，请在浏览器中完成登录（扫码 / 短信）。")
            self._allow = False
            self.user_action_required.emit(
                "便携版 Chrome 已在前台打开抖音首页（右上角会有登录按钮或二维码弹窗）。\n\n"
                "程序已自动尝试点「登录」按钮 / 切「扫码登录」；如果你仍看不到二维码：\n"
                "  · 先勾选/点掉左下角「已阅读并同意用户协议和隐私政策」\n"
                "  · 再点右上角「登录」→ 左侧或底部选「扫码登录」。\n\n"
                "请在 Chrome 中用抖音 App 扫码登录。\n"
                "▸ 登录完成后（Chrome 右上角变成头像），程序会自动检测到并关闭本窗口。\n"
                "▸ 如果自动检测超时，可手动点下方「确认登录完成」。"
            )

            # 路径 2：用户手动触发 vs 自动检测（最多 10 分钟）
            manually_triggered = False
            _iters = 600
            _idx = 0
            while _idx < _iters:
                _idx += 1

                # 用户点了"确认登录完成" → 先查强判定是否真过，不过继续等
                if self._allow:
                    self._allow = False  # 重置，避免死循环
                    if crawler._check_logged_in(driver, strong=True):
                        manually_triggered = True
                        break
                    # 强判定未过：可能用户扫了码但还在二次验证/滑块，尝试升级
                    if crawler._check_logged_in(driver, strong=False) and _upgrade_to_strong():
                        manually_triggered = True
                        break
                    # 依然没过 → 继续循环，提示用户再看一眼
                    self.log.emit(
                        "你点了「确认登录完成」但程序仍未检测到有效登录。"
                        "请回到 Chrome 看一下右上角：是不是仍显示「登录」按钮？"
                        "如果有滑块/短信验证，请在 Chrome 里完成后再点确认。"
                    )
                    self.msleep(500)
                    continue

                # 自动检测：先宽松命中 → 升级为强判定才 break
                try:
                    if crawler._check_logged_in(driver, strong=False):
                        # 宽松命中 → 尝试升级（最多 10s）
                        if _upgrade_to_strong():
                            manually_triggered = False
                            break
                        # 10s 后仍未升级 → 扫风控后继续等
                        try:
                            crawler._emit_anti_spam_if_any(
                                driver, stage=f"扫码等待中(宽松命中但强判定未过, {_idx}s)"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
                self.msleep(1000)

            # 最终判定：必须 strong=True
            if not crawler._check_logged_in(driver, strong=True):
                # 失败前扫一次风控，给出明确提示
                try:
                    crawler._emit_anti_spam_if_any(driver, stage="DouyinLoginWorker 最终判定失败")
                except Exception:
                    pass
                self.failed.emit(
                    "未检测到登录成功。\n"
                    "确认方式：登录完成后，Chrome 右上角「登录」按钮会消失、换成你的头像。\n"
                    "若出现文字点选 / 滑块 / 短信验证等安全验证，请先在 Chrome 里通过，然后再点确认。"
                )
                return

            crawler._dump_cookies(driver)
            trigger = "manual" if manually_triggered else "auto"
            self.log.emit("✅ 登录成功，Cookie 已保存到 data/douyin_cookies.(json|txt)")
            self.finished_ok.emit(trigger)
        except DouyinLoginRequired as e:
            self.failed.emit(f"环境未就绪：{e}")
        except Exception as e:
            self.failed.emit(f"登录过程出错：{type(e).__name__}: {e}")
        finally:
            try:
                if driver is not None:
                    driver.quit()
            except Exception:
                pass


class DouyinCrawlWorker(QThread):
    """爬取 + 下载抖音最新视频。未登录时 failed(DouyinLoginRequired)。"""

    finished_ok = Signal(object)   # DouyinVideo
    failed = Signal(str)
    log = Signal(str)
    progress = Signal(int, int)   # done, total   (预留，列表进度)

    def __init__(
        self,
        sec_uid: str = DEFAULT_SEC_UID,
        count: int = 3,
        download: bool = True,
        proxy: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._sec_uid = sec_uid
        self._count = max(1, count)
        self._download = download
        self._proxy = proxy

    def run(self) -> None:
        try:
            import time as _time

            crawler = DouyinCrawler(sec_uid=self._sec_uid, proxy=self._proxy, logger=self.log.emit)

            # 启动前顺手清一下"历史里有但磁盘上没文件"的死记录，避免命中后打开空文件
            try:
                cleaned = forget_broken_entries()
                if cleaned:
                    self.log.emit(f"清理了 {cleaned} 条下载历史里指向不存在文件的旧记录")
            except Exception:
                pass

            # 1) 列作品
            self.log.emit("打开个人主页，获取最新视频列表…")
            videos: List[DouyinVideo] = crawler.list_latest_videos(count=self._count)
            if not videos:
                self.failed.emit("没获取到任何视频。sec_uid 是否填对？账号是否设为私密？")
                return
            self.log.emit(
                f"✅ 作品列表拿到 {len(videos)} 条。接下来{'下载最新一条 + ffmpeg 合并' if self._download else '不下载，直接出结果'}。"
            )

            # 2) 下载第 1 条（最新一条）
            v = videos[0]
            self.log.emit(f"最新作品：《{v.desc or v.aweme_id}》")
            self.log.emit(f"播放页：{v.web_url}")

            saved_path_or_dir: Optional[str] = None
            final_output: Optional[str] = None

            # —— 重复下载检测：命中 aweme_id 且文件还在 → 直接跳过 yt-dlp ——
            if v.aweme_id:
                rec = history_lookup(key_for_douyin(v.aweme_id))
                if rec is not None:
                    self.log.emit(
                        f"⏭️  命中下载历史（aweme_id={v.aweme_id}）：{rec.output_path}"
                        f"（上次下载时间戳={rec.ts}），跳过本次下载，直接打开已存在文件"
                    )
                    saved_path_or_dir = os.path.dirname(rec.output_path)
                    final_output = rec.output_path

            if self._download and saved_path_or_dir is None:
                # 缺 yt-dlp 先友好报错，不然直接 subprocess 找不到
                try:
                    import yt_dlp  # noqa: F401
                except ImportError:
                    self.failed.emit(
                        "缺少 yt-dlp，还无法下载抖音视频。\n"
                        "解决方法（一次性）：\n"
                        "  1) 打开项目目录下的终端\n"
                        "  2) 运行：.venv\\Scripts\\pip.exe install yt-dlp\n"
                        "  3) 在 docs/requirements.txt 里把 yt-dlp 行注释打开\n\n"
                        f"暂时只拿到播放页地址：\n{v.web_url}"
                    )
                    return

                # —— 关键：下载阶段一定要明确打 2 条「阶段切换」log，UI 浮层也会随之变文案 ——
                self.log.emit("✅ 作品已拿到，进入下载阶段（yt-dlp 会实时按行回显进度，不要急）…")
                saved_path_or_dir = crawler.download_with_ytdlp(v)
                self.log.emit("✅ 下载结束（可能成功也可能失败，失败会有错误弹窗；半成品会明确列在日志里）")

                # yt-dlp 返回的是 output/douyin/ 成品目录；去找里面的最新视频文件作为最终 output
                if saved_path_or_dir:
                    final_output = find_first_file_in_dir(saved_path_or_dir)

            # 写入下载历史（只在真的有文件时写）
            if final_output and v.aweme_id:
                try:
                    history_record(
                        key_for_douyin(v.aweme_id),
                        DownloadRecord(
                            ts=int(_time.time()),
                            output_path=final_output,
                            title=v.desc or "",
                            page_url=v.web_url,
                        ),
                    )
                except Exception as e:
                    self.log.emit(f"（非致命）写入 download_history.json 失败：{type(e).__name__}: {e}")

            # 把下载目录填回 video，方便 UI 高亮
            if saved_path_or_dir:
                v = DouyinVideo(
                    aweme_id=v.aweme_id,
                    web_url=v.web_url,
                    desc=v.desc,
                    cover_url=v.cover_url + "|DIR|" + saved_path_or_dir
                    if not v.cover_url.startswith("DIR|")
                    else v.cover_url,
                )

            self.finished_ok.emit(v)
        except DouyinLoginRequired as e:
            self.failed.emit(
                "抖音未登录或登录态已过期。\n"
                f"原因：{e}\n\n"
                "请点击菜单：拓展功能 → 抖音 → 登录/重新登录。"
            )
        except CrawlerError as e:
            self.failed.emit(f"爬取失败：{e}")
        except Exception as e:
            self.failed.emit(f"抖音爬虫出错：{type(e).__name__}: {e}")


def find_first_file_in_dir(directory: str) -> Optional[str]:
    """yt-dlp download 只返回目录；UI 层高亮第一个产物文件用。"""
    d = Path(directory)
    if not d.is_dir():
        return None
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in
             (".mp4", ".mkv", ".webm", ".flv", ".mov", ".m4a", ".mp3")]
    if not files:
        return None
    return str(sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[0])
