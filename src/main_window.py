"""主窗口模块

透明无边框窗口，宠物悬浮于桌面之上。
集成状态机、动画管理器、交互管理器。
实现拖拽、右键菜单、行走等核心功能。
"""

import random
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QPoint, QUrl, QPropertyAnimation, QEasingCurve, QThread, Signal, QRect
from PySide6.QtGui import QAction, QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QLabel, QMenu, QApplication, QMessageBox, QDialog, QFormLayout,
    QVBoxLayout, QHBoxLayout, QRadioButton, QLineEdit, QSpinBox, QComboBox,
    QDialogButtonBox, QPushButton, QPlainTextEdit, QButtonGroup, QCheckBox,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QDesktopServices

from .pet_state_machine import PetState, StateMachine
from .pet_animator import PetAnimator
from .interaction import InteractionManager
from .crawler.worker import CrawlerWorker
from .crawler.gui_workers import (
    DouyinLoginWorker,
    DouyinCrawlWorker,
    find_first_file_in_dir,
)
from .crawler.douyin import DEFAULT_SEC_UID, DouyinCrawler
from .config import (
    ProxyConfig,
    PROXY_JSON,
    PROXY_MODE_DIRECT,
    PROXY_MODE_SYSTEM,
    PROXY_MODE_MANUAL,
    load_proxy_config,
    save_proxy_config,
    resolve_runtime_proxy,
    clear_proxy_config_file,
    AppConfig,
    PET_HEIGHT_DEFAULT,
    PET_HEIGHT_MIN,
    PET_HEIGHT_MAX,
    load_app_config,
    save_app_config,
    clear_app_config_file,
)


# ======================== 可调配置 ========================

# 拖拽判定阈值（像素）
DRAG_THRESHOLD = 5
# 行走速度（像素/帧）
WALK_SPEED = 2
# 行走定时器间隔（毫秒）
WALK_INTERVAL = 50
# 随机状态切换间隔（毫秒）
IDLE_INTERVAL_MIN = 5000   # 最短5秒
IDLE_INTERVAL_MAX = 15000  # 最长15秒

# 仓库地址（Gitee 建好后在 GITEE_URL 填入正确地址）
GITHUB_URL = "https://github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan"
GITEE_URL = "https://gitee.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan"

# 粉丝站 / 彩蛋
IHAN_URL = "https://ihan.com.cn"

# 抖音爬虫 - 主页地址
# 方式A（推荐）：直接粘贴完整主页 URL，程序会自动抽取 sec_uid
#   例：DOUYIN_USER_HOME = "https://www.douyin.com/user/MS4wLjABAAAAgX08v9jZ0oKv..."
# 方式B：直接把 sec_uid 贴进字符串也行，程序也能识别
#   例：DOUYIN_USER_HOME = "MS4wLjABAAAAgX08v9jZ0oKv..."
DOUYIN_USER_HOME = "https://www.douyin.com/user/MS4wLjABAAAALFdBYwOJ_j1XRBnO_qbxPfcDl2OMKGcACPIZ4Glpp1k"

# 爬虫：HTTP 代理，留空 None 表示不走代理。格式如 "http://1.1.1.1:4433"
# 建议使用 GUI「拓展功能 → 代理设置…」管理。程序启动时会从 data/proxy.json 覆盖本变量。
CRAWLER_PROXY: str | None = None
# 爬虫：是否无头模式（True 不弹浏览器窗口，运行快；False 会弹出一个最小化的 Chrome）
CRAWLER_HEADLESS: bool = False


class _FloatingLabel(QLabel):
    """圆角无边框浮层：notice 短消息（自动关）/ task 长任务（不自动关，手动 hide）。

    设计说明：**故意不启用 WA_TranslucentBackground + 外投影效果**。
    Windows 分层窗口合成路径在 QLabel + 自绘 paintEvent + 设置透明背景 + 窗口尺寸频繁变化时，
    容易把脏矩形算错（size 与 dirty 不一致），狂打 `UpdateLayeredWindowIndirect failed ... 参数错误`
    刷屏日志。这里走普通 TopLevel Tool 窗口 + `setMask` 精确剪圆角 + 自绘背景/边框，
    不做外阴影，避免触发那条有问题的合成路径。

    新增「不挡二维码」能力：
      1. anchor 参数允许浮层固定落在屏幕底部中央 / 屏幕右下角（远离 Chrome 正中央的二维码弹窗）。
      2. task 模式下支持交互：
           · 左键单击 = 临时隐藏 10s（之后再自动显示同一段文案，不会把爬虫任务状态丢掉）
           · 双击 = 永久隐藏本任务（任务结束后下一次仍会正常显示）
           · 右键 = 立即永久隐藏（效果同上双击）
         不再出现「这个浮层挡着我二维码了，但我关不掉」。
    """

    def __init__(
        self,
        text: str,
        duration_ms: int = 1500,
        mode: str = "notice",   # notice / task
        parent=None,
        *,
        anchor: str = "above_pet",   # above_pet / screen_bottom_center / screen_bottom_right
    ):
        super().__init__(text, parent)
        self._mode = mode
        self._duration_ms = duration_ms
        self._fade_in_anim: Optional[QPropertyAnimation] = None
        self._fade_out_anim: Optional[QPropertyAnimation] = None
        self._dots_timer: Optional[QTimer] = None
        self._dots = 0
        self._base_text = text
        self._radius = 14
        self._anchor = anchor

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        # —— 关键点：不要 setAttribute(WA_TranslucentBackground) ——
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

        font = QFont()
        font.setPointSize(10)
        self.setFont(font)
        self.setContentsMargins(18, 0, 18, 0)

        # task 模式：末尾三点点循环动画 + 加一行小字提示「怎么关闭」
        if mode == "task":
            self._dots_timer = QTimer(self)
            self._dots_timer.setInterval(450)
            self._dots_timer.timeout.connect(self._advance_dots)
            self._dots_timer.start()
            self._hide_temp_timer: Optional[QTimer] = None
            self._permanent_hidden = False
            self.setCursor(Qt.PointingHandCursor)
            self._repaint_text()
            self.setToolTip(
                "点击 = 隐藏 10 秒\n"
                "双击 = 本次任务永久隐藏\n"
                "右键 = 立即永久隐藏"
            )
        else:
            self.setText(text)

        # 淡入（用 windowOpacity 动画；不透明背景一样可以用整体透明度淡入淡出）
        self.setWindowOpacity(0.0)
        self._fade_in_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_in_anim.setDuration(180)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in_anim.start()

        # notice 模式：到时自动淡出 + close
        if mode == "notice" and duration_ms > 0:
            QTimer.singleShot(max(300, duration_ms), self._begin_fade_out)

    # ---- 尺寸变化时同步圆角剪裁 mask（关键：用 setMask 替代 WA_TranslucentBackground） ----

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_mask()

    def _update_mask(self):
        from PySide6.QtGui import QRegion, QBitmap
        # 用圆角矩形生成精确 mask，窗口外边缘完全透明（不会看到方角白底）
        size = self.size()
        if size.isEmpty():
            return
        pm = QBitmap(size)
        pm.fill(Qt.color0)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.color1)
        p.setPen(Qt.NoPen)
        r = min(self._radius, min(size.width(), size.height()) // 2)
        p.drawRoundedRect(QRect(0, 0, size.width(), size.height()), r, r)
        p.end()
        self.setMask(QRegion(pm))

    def setText(self, text: str):   # type: ignore[override]
        """task 模式下外部调 setText 更新基础文案，并重置三点点。"""
        if self._mode == "task":
            self._base_text = text
            self._dots = 0
            self._repaint_text()
        else:
            super().setText(text)

    def _repaint_text(self):
        if self._mode == "task":
            suffix = self._base_text + ("·" * self._dots) + (" " * (3 - self._dots))
            super().setText(suffix)
        else:
            super().setText(self._base_text)

    def _advance_dots(self):
        self._dots = (self._dots + 1) % 4
        self._repaint_text()

    # ---- 交互：点击隐藏 / 双击永久隐藏 / 右键永久隐藏 ----

    def mousePressEvent(self, event):
        if self._mode != "task":
            return
        btn = event.button()
        if btn == Qt.LeftButton:
            # 双击由 mouseDoubleClickEvent 处理，这里点一下先做临时隐藏
            self._hide_temporarily(seconds=10)
        elif btn == Qt.RightButton:
            self._hide_permanently()

    def mouseDoubleClickEvent(self, event):
        if self._mode != "task":
            return
        if event.button() == Qt.LeftButton:
            self._hide_permanently()

    def _hide_temporarily(self, seconds: int = 10):
        """临时隐藏 N 秒（之后自动把浮层重新 show 出来，不丢失任务状态）。

        用户觉得「这一行刚好挡着二维码」但又怕关掉后忘了进度，最常用这种。
        """
        try:
            self._begin_fade_out(and_close=False)
        except Exception:
            pass
        # 延时 N 秒后再淡入显示
        QTimer.singleShot(max(1, int(seconds)) * 1000, self._reshow_after_temp_hide)

    def _reshow_after_temp_hide(self):
        if self._permanent_hidden:
            return
        try:
            if hasattr(self, "_fade_in_anim") and self._fade_in_anim is not None:
                try:
                    self._fade_in_anim.stop()
                except Exception:
                    pass
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self._fade_in_anim = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade_in_anim.setDuration(180)
            self._fade_in_anim.setStartValue(0.0)
            self._fade_in_anim.setEndValue(1.0)
            self._fade_in_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._fade_in_anim.start()
        except Exception:
            pass

    def _hide_permanently(self):
        """永久隐藏本任务浮层（下一次任务仍会正常创建新的）。"""
        self._permanent_hidden = True
        try:
            self._begin_fade_out(and_close=False)
        except Exception:
            pass
        # 关闭三点点动画，彻底静默（但对象仍活着，外部 setText/hide 不会崩）
        if self._dots_timer is not None:
            try:
                self._dots_timer.stop()
            except Exception:
                pass

    # ---- 淡入淡出 & 关闭 ----

    def _begin_fade_out(self, *, and_close: bool = True):
        if self._fade_out_anim is not None:
            try:
                self._fade_out_anim.stop()
            except Exception:
                pass
            self._fade_out_anim = None
        self._fade_out_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_out_anim.setDuration(240)
        self._fade_out_anim.setStartValue(float(self.windowOpacity()))
        self._fade_out_anim.setEndValue(0.0)
        self._fade_out_anim.setEasingCurve(QEasingCurve.InCubic)
        if and_close:
            self._fade_out_anim.finished.connect(self.close)
        self._fade_out_anim.start()

    def closeEvent(self, event):
        if self._dots_timer is not None:
            try:
                self._dots_timer.stop()
            except Exception:
                pass
        super().closeEvent(event)

    def paintEvent(self, ev):
        """不透明窗口内画圆角背景 + 边框 + 文字（不做外投影，避免 UpdateLayeredWindowIndirect）。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()
        r = min(self._radius, min(rect.width(), rect.height()) // 2)

        if self._mode == "notice":
            bg = QColor(255, 255, 255)
            border = QColor(205, 208, 215)
            fg = QColor(30, 30, 30)
        else:   # task
            bg = QColor(28, 31, 42)
            border = QColor(75, 86, 120)
            fg = QColor(245, 245, 245)

        # 背景
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        p.fillPath(path, QBrush(bg))
        # 边框（内 1px，模拟内阴影外轮廓）
        pen = QPen(border, 1)
        p.setPen(pen)
        p.drawPath(path)
        # 文字
        p.setPen(fg)
        p.setFont(self.font())
        inner = rect.adjusted(self.contentsMargins().left(), 0,
                              -self.contentsMargins().right(), 0)
        p.drawText(inner, int(Qt.AlignLeft | Qt.AlignVCenter), self.text())


# ---- 代理测试线程（不阻塞 UI，不会让对话框画面卡一下） ----

class ProxyTestWorker(QThread):
    """后台 QThread 跑代理连通测试。

    为什么“第一次能用，后来再测觉得慢了好多”？
      - 旧版是**串行**尝试 3 个目标，每目标 timeout=10s；若前面目标是境外且被当前代理拉黑/绕不出去，
        就会把整个 10s 等满，你体感就是“整个测试慢了”。
      - 而且旧版是 `requests.get(整页)`，抖音/B站判定连通性根本不需要拉整页。
    修复策略：
      1) 先跑一次 **baseline（直连baidu/阿里 DNS-over-HTTPS）**，测出你本机直连的基准 RTT；
         如果你没网/系统整体网络抖，baseline 也过不了，就直接告诉你“不是代理的问题”。
      2) 真正的代理测试，把 3 个目标放在一个 **ThreadPoolExecutor(3)** 里并行做；
         单个目标 timeout=5s；先试 HEAD（只取响应头），HEAD 不支持（405/未实现）再 GET；
         任意一个成功（HTTP<400）就立刻判 PASS，让其它未完成线程 cancel 掉，避免你死等 5s*N。
    """

    line_log = Signal(str)
    finished_result = Signal(dict)

    def __init__(self, cfg: ProxyConfig, parent=None):
        super().__init__(parent)
        self._cfg = cfg

    @staticmethod
    def _head_then_get(s, url: str, timeout: float):
        """先 HEAD 省流量+省时间；HEAD 405/301/302 等不友好目标再退化成 GET 只拉很少量数据。

        注解故意不写 `requests.Session / requests.Response`——因为类定义阶段会立刻求值注解，
        但 requests 是在下面 run() 里才 import 的（写了会 NameError: name 'requests' is not defined）。
        类型提示读者按 s=requests.Session / 返回值=requests.Response 理解即可。
        """
        try:
            r = s.head(url, timeout=timeout, allow_redirects=True)
            if r.status_code < 405 or r.status_code == 405:
                # 405: HEAD 未实现 → 改 GET
                pass
            else:
                return r
        except Exception:
            # HEAD 链路不友好（很多代理/CDP 对 HEAD 行为不一致），直接改 GET
            pass
        # GET 时设置 stream=True + 只读 1KB，省下载时间
        r = s.get(url, timeout=timeout, allow_redirects=True, stream=True)
        try:
            next(r.iter_content(1024), b"")
        except Exception:
            pass
        finally:
            try:
                r.close()
            except Exception:
                pass
        return r

    def _try_one(self, s, name: str, url: str, timeout: float, parser):
        """单目标一次探测。返回 tuple(ok, name, 结果文本)。

        s 实际是 requests.Session，parser 是 (Response) -> str。这里不写类型注解避免类定义阶段 NameError。
        """
        t0 = time.perf_counter()
        try:
            r = self._head_then_get(s, url, timeout)
            r.raise_for_status()
            dt_ms = int((time.perf_counter() - t0) * 1000)
            try:
                extra = parser(r)
            except Exception:
                extra = f"HTTP {r.status_code}"
            return True, name, f"✅ {name} 通过 —— {extra}（RTT≈{dt_ms}ms）"
        except Exception as e:
            dt_ms = int((time.perf_counter() - t0) * 1000)
            msg = f"❌ {name} 失败：{type(e).__name__}: {str(e)[:120]}（耗时≈{dt_ms}ms）"
            return False, name, msg

    def run(self):
        import requests
        import concurrent.futures as _fut

        cfg = self._cfg
        proxy = cfg.url()
        self.line_log.emit(f"[模式] {cfg.mode}")

        # Session 行为和爬虫运行时完全一致（闭环）
        s = requests.Session()
        proxies = cfg.requests_proxies()
        if proxies is not None:
            s.proxies.clear()
            s.proxies.update(proxies)
        if proxy == "":
            s.trust_env = False
        self.line_log.emit(
            f"[Session] trust_env={s.trust_env}，proxies={dict(s.proxies)}（仅看类型，脱敏）"
        )

        # —— Step 0：baseline 直连一次「国内静态资源」（不经过当前 Session，绕过系统/代理），
        #    用来区分"本机整体没网/运营商抖动"和"当前代理配置真的不行"。
        baseline_ok = False
        baseline_ms = -1
        try:
            b0 = time.perf_counter()
            b = requests.Session()
            b.trust_env = False
            b.proxies.clear()
            # 阿里 DoH 返回 JSON 极小，国内快、不受境外影响
            rb = self._head_then_get(
                b, "https://223.5.5.5/resolve?name=www.baidu.com&type=A", timeout=3.5,
                parser=lambda r: "",
            )
            rb.raise_for_status()
            baseline_ms = int((time.perf_counter() - b0) * 1000)
            baseline_ok = True
            self.line_log.emit(
                f"· baseline 本机直连（绕过系统/代理）：✅ 正常（RTT≈{baseline_ms}ms，出口网络没问题）"
            )
            try:
                b.close()
            except Exception:
                pass
        except Exception as e:
            baseline_ms = int((time.perf_counter() - b0) * 1000) if 'b0' in locals() else -1
            self.line_log.emit(
                f"· baseline 本机直连：❌ 异常（{type(e).__name__}: {str(e)[:80]}，耗时≈{baseline_ms}ms）"
                "\n   👉 这一般不是代理的问题：先检查是否断网、本机防火墙/VPN 是否整体拦截外联。"
            )

        targets = [
            ("myip.ipip.net 国内IP+归属地",
             "https://myip.ipip.net",
             lambda r: f"出口信息：{(r.text or '').strip()[:80]}"),
            ("api.ipify.org 境外IP查询",
             "https://api.ipify.org",
             lambda r: f"出口 IP：{r.text.strip()[:40]}"),
            ("www.baidu.com HTTP兜底连通性",
             "https://www.baidu.com",
             lambda r: f"HTTP {r.status_code} 链路已通"),
        ]

        # —— Step 1：并行跑 3 个目标；单个超时 5s；谁先成功就整体 PASS，不等其它慢的
        self.line_log.emit(
            f"· 并行探测 {len(targets)} 个目标（单个超时 5s；任意一个通过即判 PASS）…"
        )

        per_target_timeout = 5.0
        last_err_msg = ""
        passed = None
        log_lines: list[str] = []
        with _fut.ThreadPoolExecutor(max_workers=len(targets)) as ex:
            futures = [
                ex.submit(self._try_one, s, name, url, per_target_timeout, parser)
                for name, url, parser in targets
            ]
            done_remaining = 0
            try:
                for fut in _fut.as_completed(futures, timeout=per_target_timeout + 1.0):
                    done_remaining += 1
                    ok, name, msg = fut.result()
                    log_lines.append(msg)
                    self.line_log.emit(msg)
                    if ok and passed is None:
                        passed = (name, msg)
                        # 立刻取消还没跑完的其它任务（可能慢的就是境外拉黑）
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
            except _fut.TimeoutError:
                for f in futures:
                    if not f.done():
                        f.cancel()
                timeout_note = f"⏰ 总等待超过 {per_target_timeout+1:.0f}s，已主动取消剩余探测"
                log_lines.append(timeout_note)
                self.line_log.emit(timeout_note)
                last_err_msg = timeout_note

            # 如果前面提前 break 了，等一小会儿再收日志（被 cancel 的不会 result，忽略即可）
            remaining_msgs: list[str] = []
            for fut in futures:
                if fut.cancelled():
                    continue
                if not fut.done():
                    continue
                try:
                    ok, name, msg = fut.result(timeout=0)
                except Exception:
                    continue
                if msg in log_lines:
                    continue
                remaining_msgs.append(msg)
                self.line_log.emit(msg)
            log_lines.extend(remaining_msgs)

        # 从结果里再取一次"第一个成功"；如果 as_completed break 前已记录就用它
        if passed is None:
            for msg in log_lines:
                if msg.startswith("✅"):
                    passed = ("目标命中", msg)
                    break

        try:
            s.close()
        except Exception:
            pass

        if passed is not None:
            summary = passed[1].lstrip("✅ ")
            # 把 baseline 信息拼进顶部状态条，让你一眼判断"是不是代理拖慢"
            if baseline_ok and baseline_ms >= 0:
                summary = f"✅ {summary} ｜ baseline 直连≈{baseline_ms}ms（本机网正常，代理可用）"
            else:
                summary = f"✅ {summary} ｜ baseline 异常，结果仅供参考"
        else:
            failed_last = next((ln for ln in reversed(log_lines) if ln.startswith("❌")), "")
            summary = (
                "❌ 所有目标均未通过："
                + (
                    "大概率是手动代理地址/端口填错、或当前网络被拦截。"
                    if baseline_ok else
                    "本机 baseline 直连也失败：先检查本机是否断网/VPN 是否拦截所有外联，再测代理。"
                )
            )
            if failed_last:
                summary += f"\n最近一次失败：{failed_last}"
            if last_err_msg:
                summary += f"\n{last_err_msg}"

        self.finished_result.emit({
            "ok": passed is not None,
            "summary": summary,
            "mode": cfg.mode,
            "trust_env": s.trust_env,
            "proxies": dict(s.proxies),
            "baseline_ok": baseline_ok,
            "baseline_ms": baseline_ms,
        })


class ProxySettingsDialog(QDialog):
    """右键菜单「拓展功能 → 代理设置…」弹出的对话框。

    三种模式：
      1) 跟随系统代理/VPN（默认）
      2) 强制直连（不通过任何代理）
      3) 手动配置（host / port / 用户名 / 密码 / 协议类型）

    提供「测试连接」：对多个目标站点依次尝试（国内+境外+兜底），在日志里列出每一步结果，
    顶部用一条彩色状态条直接给你结论（不用翻密密麻麻日志）。
    保存时写入 data/proxy.json（gitignore 已忽略）。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("代理设置")
        self.resize(560, 480)
        self._cfg: ProxyConfig = load_proxy_config()
        # 后台测试线程引用（防 GC；同时禁止同一配置框里并发）
        self._test_thread: Optional[ProxyTestWorker] = None

        root = QVBoxLayout(self)

        # ---- 模式选择 ----
        grp_mode = QButtonGroup(self)
        self.rb_system = QRadioButton("跟随系统（推荐）")
        self.rb_system.setToolTip(
            "把「走不走代理」交给系统决定。\n"
            "会读取：Windows 系统代理开关 / HTTP(S)_PROXY 环境变量 / 企业 PAC 脚本。\n"
            "日常用 Chrome 能打开的网站，爬虫也能以同样的网络出口访问。\n"
            "注：对全局 VPN（虚拟网卡/TUN 模式）无差别，因为是路由表层面劫持。"
        )
        self.rb_direct = QRadioButton("强制直连")
        self.rb_direct.setToolTip(
            "忽略一切外部代理信号源：Windows 系统代理开关、HTTP_PROXY 环境变量、企业 PAC、Chrome 系统代理设置全部跳过，\n"
            "直接从本机网卡裸网出去（进程级禁用代理解析）。\n"
            "适用：开了 Clash/梯子但不想让爬虫绕一圈（B 站/抖音国内直连更稳更快）。\n"
            "对虚拟网卡级全局 VPN 无效，需要先关掉 VPN。"
        )
        self.rb_manual = QRadioButton("手动配置")
        self.rb_manual.setToolTip(
            "手动填一个独立代理服务器（HTTP / HTTPS / SOCKS5 / SOCKS5h），与系统代理完全无关。\n"
            "支持账号密码（勾选「明文存盘」就写进 data/proxy.json，不勾选则仅当前会话生效）。\n"
            "点「测试连接」可立刻验证出口 IP 是否正确。"
        )
        for i, rb in enumerate((self.rb_system, self.rb_direct, self.rb_manual)):
            grp_mode.addButton(rb, i)
            root.addWidget(rb)

        # ---- 手动输入行 ----
        form = QFormLayout()
        self.ed_host = QLineEdit()
        self.ed_host.setPlaceholderText("例：127.0.0.1 或 proxy.example.com")
        self.ed_host.setToolTip("代理服务器地址，填 IP 或域名都行。")
        self.sp_port = QSpinBox()
        self.sp_port.setRange(0, 65535)
        self.sp_port.setSpecialValueText("未填写")
        self.sp_port.setToolTip("代理端口，通常 Clash 是 7890、常见 SOCKS 是 1080。")
        self.ed_user = QLineEdit()
        self.ed_user.setPlaceholderText("可留空")
        self.ed_user.setToolTip("仅当代理服务器需要 Basic 认证时填写。")
        self.ed_pass = QLineEdit()
        self.ed_pass.setEchoMode(QLineEdit.Password)
        self.ed_pass.setPlaceholderText("可留空")
        self.ed_pass.setToolTip("认证密码。勾选下方的明文存盘开关决定是否写入磁盘。")
        self.cb_scheme = QComboBox()
        self.cb_scheme.addItems(["http", "https", "socks5", "socks5h"])
        self.cb_scheme.setToolTip(
            "http/https：最常用，绝大多数 HTTP/HTTPS 代理都选它。\n"
            "socks5：标准 SOCKS5（目标域名由本机 DNS 解析后再告诉代理）。\n"
            "socks5h：推荐给远程 SOCKS5 —— 目标域名也交给代理 DNS 解析，绕过本地 DNS 污染。"
        )
        self.cb_savepass = QCheckBox("明文存盘（账号密码写入 data/proxy.json）")
        self.cb_savepass.setToolTip(
            "勾选：保存后下次打开程序不用再输入账号密码（风险：proxy.json 文件是可读的明文）。\n"
            "不勾选：仅本次运行的会话期间生效，关闭程序即丢失。"
        )
        self.cb_savepass.setChecked(True)

        form.addRow("代理协议", self.cb_scheme)
        form.addRow("服务器 Host", self.ed_host)
        form.addRow("端口 Port", self.sp_port)
        form.addRow("用户名", self.ed_user)
        form.addRow("密码", self.ed_pass)
        form.addRow("", self.cb_savepass)
        form_box = QWidget()
        form_box.setLayout(form)
        root.addWidget(form_box)

        def update_enable():
            manual = self.rb_manual.isChecked()
            form_box.setEnabled(manual)
        self.rb_manual.toggled.connect(update_enable)

        # ---- 顶部状态条（每次测试刷新） ----
        self.lbl_status = QLabel("尚未测试：点「测试连接」可立刻检查当前配置是否可用")
        self.lbl_status.setContentsMargins(12, 10, 12, 10)
        self._apply_status_style("gray")
        root.addWidget(self.lbl_status)

        # ---- 测试按钮区 ----
        row = QHBoxLayout()
        self.btn_help = QPushButton("? 三种模式区别")
        self.btn_help.setMaximumWidth(140)
        self.btn_help.clicked.connect(self._on_show_help)
        self.btn_test = QPushButton("测试连接")
        self.btn_test.setToolTip("依次尝试多个目标站点（境外/国内/兜底），有一个通过就判定当前配置可用。")
        self.btn_test.clicked.connect(self._on_test)
        row.addWidget(self.btn_help)
        row.addWidget(self.btn_test)
        row.addStretch(1)
        root.addLayout(row)

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlaceholderText(
            "点「测试连接」后会显示每一步的尝试记录（仅保留本次结果，不会一段一段往下加）。"
        )
        root.addWidget(self.txt_log, 1)

        # ---- 底部按钮 ----
        row_bottom = QHBoxLayout()
        self.btn_clear_proxy = QPushButton("清除代理配置文件")
        self.btn_clear_proxy.setToolTip("删除 data/proxy.json（里面可能包含账号密码明文），恢复默认跟随系统。")
        self.btn_clear_proxy.clicked.connect(self._on_clear_proxy_file)
        row_bottom.addWidget(self.btn_clear_proxy)
        row_bottom.addStretch(1)
        root.addLayout(row_bottom)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Reset, self)
        bb.button(QDialogButtonBox.Save).setText("保存并应用")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.button(QDialogButtonBox.Reset).setText("恢复默认（跟随系统）")
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Reset).clicked.connect(self._on_reset)
        root.addWidget(bb)

        # 用当前 cfg 回填 UI
        self._fill_from_cfg()
        update_enable()

    def _apply_status_style(self, color: str):
        """color: gray(未测)/green(ok)/red(failed)/blue(running)"""
        bg = {
            "gray":  "#F1F3F5",
            "green": "#E7F8EE",
            "red":   "#FDECEA",
            "blue":  "#EAF1FD",
        }[color]
        fg = {
            "gray":  "#4D5159",
            "green": "#1E7F49",
            "red":   "#B42318",
            "blue":  "#1D4ED8",
        }[color]
        border = {
            "gray":  "#D0D5DD",
            "green": "#A5E0BA",
            "red":   "#F4B4AB",
            "blue":  "#B7CDF7",
        }[color]
        self.lbl_status.setStyleSheet(
            f"color: {fg};"
            f"background-color: {bg};"
            f"border: 1px solid {border};"
            "border-radius: 8px;"
            "font-size: 13px;"
        )

    # ---- UI <-> cfg ----

    def _fill_from_cfg(self):
        mode = self._cfg.mode
        if mode == PROXY_MODE_DIRECT:
            self.rb_direct.setChecked(True)
        elif mode == PROXY_MODE_MANUAL:
            self.rb_manual.setChecked(True)
        else:
            self.rb_system.setChecked(True)
        self.ed_host.setText(self._cfg.host)
        self.sp_port.setValue(self._cfg.port or 0)
        self.ed_user.setText(self._cfg.username)
        self.ed_pass.setText(self._cfg.password)
        idx = self.cb_scheme.findText(self._cfg.scheme)
        if idx >= 0:
            self.cb_scheme.setCurrentIndex(idx)

    def _collect_cfg(self) -> ProxyConfig:
        cfg = ProxyConfig(
            mode=(
                PROXY_MODE_MANUAL if self.rb_manual.isChecked()
                else PROXY_MODE_DIRECT if self.rb_direct.isChecked()
                else PROXY_MODE_SYSTEM
            ),
            host=self.ed_host.text().strip(),
            port=int(self.sp_port.value()),
            username=self.ed_user.text().strip(),
            password=self.ed_pass.text() if self.cb_savepass.isChecked() else "",
        )
        cfg.extras["scheme"] = self.cb_scheme.currentText()
        return cfg

    # ---- 按钮 ----

    def _on_reset(self):
        self._cfg = ProxyConfig()  # 默认 system
        self._fill_from_cfg()
        self.txt_log.clear()
        self._apply_status_style("gray")
        self.lbl_status.setText("已恢复默认「跟随系统」，如需验证可以点测试连接")

    def _on_show_help(self):
        text = (
            "代理模式的选择，只影响「爬虫相关的出口（B 站/抖音爬取 + yt-dlp 下载）」，\n"
            "不影响桌面宠物动画、行走、投喂这些本地功能。\n\n"
            "三种模式的真正区别，在于「是否响应下面这些外部代理信号源」：\n\n"
            "  1. Windows 系统代理开关（Clash/v2rayN 的「系统代理」按钮就是改这个注册表项）\n"
            "  2. HTTP_PROXY / HTTPS_PROXY / ALL_PROXY 环境变量\n"
            "  3. 企业 PAC / WPAD 自动检测脚本\n"
            "  4. yt-dlp 的全局配置文件 %APPDATA%\\yt-dlp\\config\n\n"
            "─────────────────────────────\n"
            "◆ 跟随系统（推荐，95% 场景）\n"
            "   响应上面 1~4 所有信号源。\n"
            "   爬虫表现和你默认 Chrome/Edge 浏览器一模一样。\n"
            "   你日常浏览器能打开什么站，爬虫就能打开什么站。\n\n"
            "◆ 强制直连\n"
            "   忽略上面 1~4 所有信号源：进程级禁用代理解析，本机 DNS → 本机 TCP 直接出去。\n"
            "   适用场景：Clash 开着系统代理，但我爬 B 站/抖音就想走国内直连，更快更稳。\n"
            "   ❗ 对「全局 VPN（虚拟网卡/TUN 模式）」无效，因为 VPN 是在 Windows 路由表层面劫持流量，进程没有能力绕过。想彻底直连先关 VPN。\n\n"
            "◆ 手动配置\n"
            "   完全忽略上面 1~4，固定走你填的代理服务器。\n"
            "   常用协议：http（绝大多数代理）/ socks5h（远程 SOCKS5，推荐，连 DNS 解析也交给代理避开本地 DNS 污染）。\n"
            "   点「测试连接」可立刻验证出口 IP 是不是你期望的代理出口。\n\n"
            "─────────────────────────────\n"
            "如果你不知道选什么 → 保持默认「跟随系统」即可。\n"
            "隐私提示：手动模式里的账号密码，勾选明文存盘会写入 data/proxy.json，\n"
            "            不想写盘就取消勾选（仅本次会话生效，关掉程序即丢）；\n"
            "            随时可以点本对话框底部的「清除代理配置文件」一键删掉该文件。\n"
        )
        box = QMessageBox(self)
        box.setWindowTitle("代理三种模式 · 详细说明")
        box.setText(text)
        box.setIcon(QMessageBox.Information)
        box.exec()

    def _on_clear_proxy_file(self):
        """删除 data/proxy.json 并恢复默认，同时让外部应用立刻生效。"""
        from .config import PROXY_JSON
        import os
        if not os.path.isfile(PROXY_JSON):
            QMessageBox.information(
                self,
                "清除完成",
                f"{PROXY_JSON}\n本来就不存在（从未手动保存过 / 已经清除过）。",
            )
            # 界面依然恢复默认，避免 UI 和内存态不一致
            self._cfg = ProxyConfig()
            self._fill_from_cfg()
            return

        box = QMessageBox(self)
        box.setWindowTitle("确认清除代理配置文件")
        box.setIcon(QMessageBox.Warning)
        box.setText(
            f"即将删除以下文件（里面可能包含明文写的代理账号密码）：\n\n"
            f"  {PROXY_JSON}\n\n"
            f"删除后程序立刻恢复默认「跟随系统」。确定删除吗？"
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("确认删除")
        box.button(QMessageBox.Cancel).setText("取消")
        if box.exec() != QMessageBox.Yes:
            return
        try:
            os.remove(PROXY_JSON)
        except OSError as e:
            QMessageBox.warning(self, "删除失败", f"{type(e).__name__}: {e}")
            return

        # 恢复默认并同步运行时 CRAWLER_PROXY
        self._cfg = ProxyConfig()
        self._fill_from_cfg()
        global CRAWLER_PROXY
        CRAWLER_PROXY = resolve_runtime_proxy(self._cfg)

        QMessageBox.information(
            self,
            "清除完成",
            f"已删除 {PROXY_JSON}\n当前已恢复默认：跟随系统代理 / VPN。",
        )

    def _on_test(self):
        """代理连接测试 — 后台 QThread 跑，不卡对话框画面；每次点测试清空日志，只保留本次结果。

        顶部 status bar 给你一行大结论（✅/❌），下面 txt_log 列每个目标的尝试记录。
        """
        # 上次还在跑？不允许并发，按钮点了直接忽略
        if self._test_thread is not None and self._test_thread.isRunning():
            return

        cfg = self._collect_cfg()
        # 手动模式下 host+port 为空 → 直接提示，不启动线程（省时间+省日志噪音）
        if cfg.mode == PROXY_MODE_MANUAL and (not cfg.host or cfg.port <= 0):
            self.txt_log.clear()
            self._apply_status_style("red")
            self.lbl_status.setText("❌ 手动模式需要先填 Host 和 Port 才能测试")
            self.txt_log.appendPlainText(
                "[错误] 手动模式下 Host/Port 必填。先在上面的表单里填好，再点测试。"
            )
            return

        # 每次点先清空，不要一段一段往下加
        self.txt_log.clear()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("测试中…")
        self._apply_status_style("blue")
        self.lbl_status.setText("🔵 测试中：依次尝试多个目标站点，耗时最长 30s…")
        # 立即让 UI 画出来，避免用户看到"按钮还没灰就卡一下"
        QApplication.processEvents()

        w = ProxyTestWorker(cfg, self)
        self._test_thread = w

        w.line_log.connect(lambda line: self.txt_log.appendPlainText(line))

        def on_result(res: dict):
            self.btn_test.setEnabled(True)
            self.btn_test.setText("测试连接")
            ok = bool(res["ok"])
            self._apply_status_style("green" if ok else "red")
            self.lbl_status.setText(res["summary"])
            # 日志底部追加一行总结，方便复制给我查问题
            self.txt_log.appendPlainText("")
            self.txt_log.appendPlainText("—" * 32)
            self.txt_log.appendPlainText(
                "总结：" + res["summary"]
            )

        w.finished_result.connect(on_result)
        w.start()

    def _on_save(self):
        cfg = self._collect_cfg()
        # 校验：manual 模式下必填 host + port
        if cfg.mode == PROXY_MODE_MANUAL and (not cfg.host or cfg.port <= 0):
            QMessageBox.warning(
                self,
                "手动配置缺失",
                "选择「手动配置代理」后，Host 和 Port 必须填写。\n"
                "不确定的话选「跟随系统代理 / 系统 VPN」即可。",
            )
            return
        saved_path = save_proxy_config(cfg)
        # 同步运行时变量
        global CRAWLER_PROXY
        CRAWLER_PROXY = resolve_runtime_proxy(cfg)
        QMessageBox.information(
            self,
            "保存成功",
            f"代理配置已保存到：{saved_path}\n\n"
            f"当前生效：{self._describe(cfg)}\n\n"
            "下一次启动爬虫任务（B 站 / 抖音）会立刻采用这个配置。",
        )
        self.accept()

    @staticmethod
    def _describe(cfg: ProxyConfig) -> str:
        if cfg.mode == PROXY_MODE_SYSTEM:
            return "跟随系统代理 / 系统 VPN"
        if cfg.mode == PROXY_MODE_DIRECT:
            return "强制直连（不通过任何代理）"
        auth = "带认证" if cfg.username else "无认证"
        return f"手动 {cfg.scheme}://{cfg.host}:{cfg.port} ({auth})"


class ClearPrivacyDialog(QDialog):
    """拓展功能 → 清除隐私数据 …

    可勾选 4 类本地隐私文件：
      A) 代理配置 data/proxy.json（可能含明文账号密码）
      B~D) 抖音登录态 3 处（Profile-Douyin 目录 / json / txt）

    每一项带路径说明；点确认后会显示"成功删除 / 本来就不存在 / 删除失败"三条汇总。
    """

    class Item:
        __slots__ = ("key", "title", "desc", "path")

        def __init__(self, key, title, desc, path):
            self.key = key
            self.title = title
            self.desc = desc
            self.path = path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清除本地隐私数据")
        self.resize(560, 460)

        # 先把路径准备好
        import os
        from .resource_manager import get_data_path
        dc = DouyinCrawler()
        locs = dc.login_data_locations()
        from .config import SETTINGS_JSON
        self._items: list[ClearPrivacyDialog.Item] = [
            ClearPrivacyDialog.Item(
                "proxy_json",
                "代理配置文件 data/proxy.json",
                "手动模式下写入的 Host / Port / 账号 / 密码（若勾选了明文存盘）",
                PROXY_JSON,
            ),
            ClearPrivacyDialog.Item(
                "settings_json",
                "显示偏好设置 data/settings.json",
                "记录你改的「窗口置顶」「宠物显示高度」。\n删除后下次启动会自动恢复 240 px / 默认置顶。",
                SETTINGS_JSON,
            ),
            ClearPrivacyDialog.Item(
                "douyin_cookie_json",
                "抖音 Cookie JSON",
                DouyinCrawler.LOGIN_LOCATIONS_DESC["cookies_json"],
                locs["cookies_json"],
            ),
            ClearPrivacyDialog.Item(
                "douyin_cookie_txt",
                "抖音 Cookie TXT（yt-dlp 用）",
                DouyinCrawler.LOGIN_LOCATIONS_DESC["cookies_netscape"],
                locs["cookies_netscape"],
            ),
            ClearPrivacyDialog.Item(
                "douyin_profile_dir",
                "抖音 Chrome 独立用户资料目录",
                DouyinCrawler.LOGIN_LOCATIONS_DESC["chrome_profile_dir"],
                locs["chrome_profile_dir"],
            ),
            ClearPrivacyDialog.Item(
                "crawler_tmp",
                "爬虫临时文件 data/tmp/",
                "下载中断/失败留下的半成品（.part / .ytdl / 未合并的音视频分片）。\n勾选后会递归删除 data/tmp/ 下所有子目录。",
                os.path.join(get_data_path("tmp")),
            ),
        ]
        root = QVBoxLayout(self)
        lab = QLabel(
            "勾选要删除的本地隐私文件（删除后不可恢复）：\n"
            "说明：这些文件都会被 .gitignore 忽略，不会提交到 Git 仓库。\n"
            "如果打算把项目发给别人/或者准备公开打包，建议在此一键清干净再操作。"
        )
        lab.setWordWrap(True)
        root.addWidget(lab)

        self._cbs: dict[str, QCheckBox] = {}
        for it in self._items:
            cb = QCheckBox()
            import os
            exist = os.path.exists(it.path)
            suffix = "  （当前不存在）" if not exist else ""
            cb.setText(f"☐  {it.title}{suffix}")
            cb.setToolTip(f"{it.desc}\n路径：{it.path}")
            cb.setChecked(True if exist else False)
            self._cbs[it.key] = cb
            root.addWidget(cb)

        # 额外备注
        note = QLabel(
            "⚠️  删除抖音 Chrome 用户资料目录前，请先关闭由本程序启动的 Chrome 窗口，\n"
            "       否则文件被占用时会跳过该项并在汇总里提示。"
        )
        note.setStyleSheet("color:#a55;")
        note.setWordWrap(True)
        root.addWidget(note)

        root.addStretch(1)

        # 按钮
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.button(QDialogButtonBox.Ok).setText("清除已勾选项")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self._on_confirm)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _on_confirm(self):
        picked_keys = [k for k, cb in self._cbs.items() if cb.isChecked()]
        if not picked_keys:
            QMessageBox.information(self, "未勾选", "请至少勾选一项要删除的内容。")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("二次确认")
        lines = ["确认删除以下勾选的本地隐私内容吗？删除后不可恢复：\n"]
        for it in self._items:
            if it.key in picked_keys:
                lines.append(f"  · {it.title}")
                lines.append(f"      路径: {it.path}")
        lines.append("\n提示：抖音登录态删除后，下次使用抖音爬虫前需要重新扫码登录。")
        box.setText("\n".join(lines))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("确认删除")
        box.button(QMessageBox.Cancel).setText("取消")
        if box.exec() != QMessageBox.Yes:
            return

        # 执行删除
        import os
        ok, skipped, failed = [], [], []
        dc = DouyinCrawler()

        if "proxy_json" in picked_keys:
            if clear_proxy_config_file():
                ok.append(f"[代理配置] {PROXY_JSON}")
            else:
                failed.append(f"[代理配置] 删不掉 {PROXY_JSON}（可能被占用）")
        if "settings_json" in picked_keys:
            if clear_app_config_file():
                ok.append(f"[显示设置] data/settings.json（下次启动自动恢复默认显示偏好）")
            else:
                failed.append(f"[显示设置] data/settings.json —— 删除失败")
        # 抖音 3 处：直接复用 DouyinCrawler.clear_login_data 但只删选中的
        if "douyin_profile_dir" in picked_keys or "douyin_cookie_json" in picked_keys or "douyin_cookie_txt" in picked_keys:
            # clear_login_data 是"全删"三选三的；为了只删勾选，这里拆开来删
            import shutil
            if "douyin_profile_dir" in picked_keys:
                d = dc.login_data_locations()["chrome_profile_dir"]
                if os.path.isdir(d):
                    try:
                        shutil.rmtree(d)
                        ok.append(f"[抖音Profile] {d}")
                    except OSError:
                        failed.append(f"[抖音Profile] {d} —— 删除失败（Chrome 还在占用？请先关闭窗口）")
                else:
                    skipped.append(f"[抖音Profile] {d} —— 本来就不存在")
            for pick_key, attr in (
                ("douyin_cookie_json", "cookies_json"),
                ("douyin_cookie_txt", "cookies_netscape"),
            ):
                if pick_key in picked_keys:
                    f = dc.login_data_locations()[attr]
                    if os.path.isfile(f):
                        try:
                            os.remove(f)
                            ok.append(f"[{attr}] {f}")
                        except OSError as e:
                            failed.append(f"[{attr}] {f} —— {type(e).__name__}: {e}")
                    else:
                        skipped.append(f"[{attr}] {f} —— 本来就不存在")

        # 爬虫临时文件
        if "crawler_tmp" in picked_keys:
            tmp_base = get_data_path("tmp")
            if os.path.isdir(tmp_base):
                import shutil
                cleared = 0
                for sub in os.listdir(tmp_base):
                    sub_path = os.path.join(tmp_base, sub)
                    try:
                        if os.path.isdir(sub_path):
                            shutil.rmtree(sub_path)
                        else:
                            os.remove(sub_path)
                        cleared += 1
                    except OSError:
                        failed.append(f"[tmp] {sub_path} —— 删除失败（文件被占用？）")
                if cleared:
                    ok.append(f"[临时文件] data/tmp/ 下清除了 {cleared} 个子目录/文件")
                else:
                    skipped.append("[临时文件] data/tmp/ —— 没有可清除的内容")
            else:
                skipped.append("[临时文件] data/tmp/ —— 本来就不存在")

        # 让 PetWindow 立刻同步 CRAWLER_PROXY（避免还挂着老的手动代理）
        global CRAWLER_PROXY
        if "proxy_json" in picked_keys:
            CRAWLER_PROXY = resolve_runtime_proxy(load_proxy_config())

        # 汇总
        parts = []
        if ok:
            parts.append("✅ 成功删除：\n" + "\n".join("  " + x for x in ok))
        if skipped:
            parts.append("ℹ️  本来就不存在（跳过）：\n" + "\n".join("  " + x for x in skipped))
        if failed:
            parts.append("❌ 失败：\n" + "\n".join("  " + x for x in failed))
        if not parts:
            parts.append("没有什么可删除的（勾选项都已不存在）。")
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("清除结果汇总")
        msg_box.setIcon(QMessageBox.Information if not failed else QMessageBox.Warning)
        msg_box.setText("\n\n".join(parts))
        msg_box.exec()

        # 有成功删除 → 关闭对话框；只有跳过或失败 → 不关让用户再选
        if ok:
            self.accept()


class PetSizeSettingsDialog(QDialog):
    """右键菜单「设置 → 调整宠物大小…」对话框。

    用一个 QSpinBox 直接选 120~480 px 高度；下面三个预设按钮一键填常用档位（180 / 240 / 320）。
    预览文字会实时告知「改完后物品高度 ≈ 多少」。
    确定后写入 data/settings.json 并由 PetWindow 即时生效。
    """

    def __init__(self, current_height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("调整宠物大小")
        self.setMinimumWidth(360)

        form = QFormLayout(self)

        self._height_spin = QSpinBox(self)
        self._height_spin.setRange(PET_HEIGHT_MIN, PET_HEIGHT_MAX)
        self._height_spin.setSuffix(" px")
        self._height_spin.setSingleStep(10)
        self._height_spin.setValue(max(PET_HEIGHT_MIN, min(PET_HEIGHT_MAX, int(current_height))))
        self._height_spin.setToolTip(
            f"范围 {PET_HEIGHT_MIN} - {PET_HEIGHT_MAX} 像素。\n"
            f"默认 {PET_HEIGHT_DEFAULT} px（= 3:4 素材缩到 180×240 显示）。\n"
            f"物品图会按宠物高度的 1/3 自动联动缩放，不用单独设置。"
        )

        # 预设档位
        presets_row = QHBoxLayout()
        for label, value in (("小 180", 180), ("中 240（默认）", 240), ("大 320", 320)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, v=value: self._height_spin.setValue(v))
            presets_row.addWidget(btn)

        # 预览提示
        self._preview = QLabel(self._make_preview_text(self._height_spin.value()))
        self._preview.setStyleSheet("color: #555; font-size: 9pt;")
        self._height_spin.valueChanged.connect(
            lambda v: self._preview.setText(self._make_preview_text(v))
        )

        # 按钮组
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults,
            parent=self,
        )
        buttons.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            lambda: self._height_spin.setValue(PET_HEIGHT_DEFAULT)
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form.addRow("宠物显示高度：", self._height_spin)
        form.addRow("预设档位：", presets_row)
        form.addRow("预览", self._preview)
        form.addRow(buttons)

    # ------------------------------------------------------------------ internals

    def _make_preview_text(self, pet_h: int) -> str:
        item_h = max(40, int(pet_h / 3))
        ratio = "3:4 素材 → 约 {w}×{h}".format(w=int(pet_h * 3 / 4), h=pet_h)
        return (
            f"人物（{ratio}）\n"
            f"骨头 / 葡萄汁 / 豆腐 等物品 → 高约 {item_h} px（联动自动缩放）"
        )

    @property
    def selected_height(self) -> int:
        return int(self._height_spin.value())


class PetWindow(QWidget):
    """宠物主窗口"""

    def __init__(self):
        super().__init__()

        # 启动时从 data/settings.json 加载 UI 显示设置
        self._app_cfg: AppConfig = load_app_config()

        # 启动时从 data/proxy.json 加载代理配置
        proxy_cfg = load_proxy_config()
        global CRAWLER_PROXY
        CRAWLER_PROXY = resolve_runtime_proxy(proxy_cfg)

        # 窗口设置：无边框 + 透明背景 + Qt.Tool（任务栏不占位）。
        # 置顶默认开，但用户可以在菜单「设置 → 窗口置顶」里切换，所以这里只给一个初值。
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._app_cfg.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 用于显示动画的 Label
        self._label = QLabel(self)

        # 核心组件
        self._state_machine = StateMachine(PetState.IDLE)
        self._animator = PetAnimator(self._label)
        self._interaction = InteractionManager(
            self._state_machine, self._animator, self
        )

        # 先把尺寸 apply 到 animator（确保 _init_ui.play(IDLE) 按用户设置的高度显示）
        from .pet_animator import apply_app_config as _apply_animator_cfg
        _apply_animator_cfg(self._app_cfg)

        # 拖拽状态
        self._dragging = False
        self._drag_offset = QPoint()
        self._press_pos = QPoint()

        # 行走方向
        self._walk_direction = 1  # 1=向右, -1=向左

        # 定时器
        self._walk_timer = QTimer(self)
        self._walk_timer.timeout.connect(self._on_walk)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)

        # 连接状态变化信号
        self._state_machine.state_changed.connect(self._on_state_changed)

        # 爬虫后台线程（一次只允许一个跑；保存引用防止 GC）
        self._crawler_worker: CrawlerWorker | DouyinLoginWorker | DouyinCrawlWorker | None = None

        # 非模态浮层（内置 QLabel，避免独立 Popup 留屏、叠层、GC 不及时导致的残留遮罩）
        # _floating_notice:  1~2s 自动消失的短提示（一次性，不阻塞事件循环）
        # _task_overlay:     爬虫等长任务时的"持久状态浮层"，任务未完成时持续显示
        self._floating_notice: Optional[_FloatingLabel] = None
        self._task_overlay: Optional[_FloatingLabel] = None
        # 当前长任务浮层的"锚点偏好"
        self._task_overlay_anchor: str = "above_pet"
        # —— 长任务浮层的状态机：_task_stage 用来防止同一个阶段重复刷屏
        #    只有当 log 触发了"新阶段"，才会更新浮层文案。旧阶段再次出现的 log 直接忽略。
        self._task_stage: str = ""

        # 记录窗口置顶的 QAction（勾选状态与当前设置联动）
        self._action_always_on_top: Optional[QAction] = None

        # 初始化
        self._init_ui()
        self._start_idle()

    # ======================================================================
    # 显示设置：窗口置顶 + 宠物高度；持久化到 data/settings.json，即时生效
    # ======================================================================

    def _save_app_cfg_and_notice(self, tip: str) -> None:
        """存盘 + 右上角轻提示（成功写入文件路径）。"""
        path = save_app_config(self._app_cfg)
        self._show_notice(f"✅ {tip}（已保存到 data/settings.json）", duration_ms=1600)
        _ = path  # 写入路径已在 _show_notice 或之后 UI 上显式展示过

    def _toggle_always_on_top(self, checked: bool) -> None:
        """切换窗口是否置顶（用户勾选后立刻生效，存盘保留下次启动）。"""
        self._app_cfg.always_on_top = bool(checked)

        # 改 WindowStaysOnTopHint 必须重新 setWindowFlags，Qt 不支持单独动态开关这一位后不 hide/show。
        visible = self.isVisible()
        old_pos = self.pos()

        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        # setWindowFlags 后窗口会被 Qt 隐藏，手动 move 回原位 + show
        self.move(old_pos)
        if visible:
            self.show()

        if self._action_always_on_top is not None:
            self._action_always_on_top.setChecked(checked)
        self._save_app_cfg_and_notice(f"窗口置顶 = {'开' if checked else '关'}")

    def _open_pet_size_settings(self) -> None:
        """打开「调整宠物大小」对话框。确定后立刻按新高度重绘宠物 + 窗口大小 + 存盘。"""
        dlg = PetSizeSettingsDialog(current_height=self._app_cfg.pet_height, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_h = dlg.selected_height
        if new_h == self._app_cfg.pet_height:
            return  # 没变就不搞一遍

        old_center_x = self.x() + self.width() // 2
        old_bottom = self.y() + self.height()

        # 1) 写 AppConfig + 应用到 animator 运行时
        self._app_cfg.pet_height = new_h
        from .pet_animator import apply_app_config as _apply_animator_cfg
        _apply_animator_cfg(self._app_cfg)

        # 2) 对当前显示的帧即时应用新尺寸
        self._animator.apply_sizes_now(self._app_cfg.pet_height, self._app_cfg.item_height)

        # 3) 跟随 label 调整窗口固定大小
        label_size = self._label.size()
        self.setFixedSize(label_size)

        # 4) 位置：按"人物的脚底 / 水平中线"对齐旧位置，避免改大小时人物在屏幕上"跳"
        new_x = max(0, old_center_x - self.width() // 2)
        new_y = max(0, old_bottom - self.height())
        self.move(new_x, new_y)

        # 5) 持久化 + 提示
        self._save_app_cfg_and_notice(
            f"宠物显示高度 = {self._app_cfg.pet_height} px"
        )

    def _init_ui(self):
        """初始化 UI"""
        # 播放待机动画（animator 会自动设置 label 尺寸）
        self._animator.play(PetState.IDLE)

        # 根据动画管理器设置的 label 尺寸调整窗口
        label_size = self._label.size()
        self.setFixedSize(label_size)

        # 初始位置：屏幕中下方
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() // 2 - self.width() // 2
        y = screen.height() - self.height() - 50
        self.move(x, y)

    # ---------- 浮层：短通知 / 长任务遮罩 ----------

    def _floating_geometry(
        self,
        above: bool = True,
        width: int = 380,
        *,
        anchor: str = "above_pet",   # above_pet / screen_bottom_center / screen_bottom_right
        height: int = 44,
    ) -> tuple[int, int, int, int]:
        """计算浮层在屏幕上的位置。

        - `above_pet`: 在宠物上方 / 下方（老行为）
        - `screen_bottom_center`: 屏幕可用区域底部居中（不跟随宠物，不挡 Chrome 正中央二维码）
        - `screen_bottom_right`: 屏幕右下角（最安全，距离 Chrome 弹窗最远；抖音登录/扫码建议用这个）
        """
        screen = QApplication.primaryScreen().availableGeometry()
        self_w = self.width()
        self_x = self.x()
        self_y = self.y()
        # 浮层宽度 minimum 380，最大不超过屏幕 80%
        width = max(300, min(width, int(screen.width() * 0.8)))

        if anchor == "screen_bottom_center":
            x = screen.left() + (screen.width() - width) // 2
            y = screen.bottom() - height - 18
            return x, y, width, height
        if anchor == "screen_bottom_right":
            x = screen.right() - width - 18
            y = screen.bottom() - height - 18
            return x, y, width, height

        # 原行为：跟随宠物
        x = self_x + (self_w - width) // 2
        # 贴边保护
        x = max(screen.left() + 16, min(screen.right() - width - 16, x))
        if above:
            y = self_y - 54            # 宠物顶部上面一点点的位置
            # 如果太靠顶部放不下，就放下面
            if y - 16 < screen.top():
                y = self_y + self.height() + 10
        else:
            y = self_y + self.height() + 10
        return x, y, width, 44

    def _show_notice(self, text: str, duration_ms: int = 1500):
        """1~2 秒自动关闭的轻提示（内置 QLabel，非模态不阻塞事件循环）。"""
        if self._floating_notice is not None:
            try:
                self._floating_notice.close()
            except Exception:
                pass
            self._floating_notice = None
        lb = _FloatingLabel(text, duration_ms=duration_ms, mode="notice", parent=None)
        lb.setAttribute(Qt.WA_DeleteOnClose, True)
        x, y, w, h = self._floating_geometry(above=True)
        lb.move(x, y - 10)          # notice 在 task_overlay 上面一点点（不叠一起）
        lb.resize(w, h)
        lb.show()
        self._floating_notice = lb

    def _task_overlay_show(
        self,
        text: str,
        *,
        anchor: str | None = None,   # None=沿用当前任务锚点；显式传值则会把任务锚点一起更新
    ):
        """长任务进行中的持久浮层：任务未完成时一直显示；调用者负责 hide。

        - 普通爬虫任务默认 `above_pet`：跟随宠物（原行为）。
        - 抖音登录/扫码等「会弹 Chrome 二维码窗口」的阶段：传 `screen_bottom_right`，
          让浮层固定落在屏幕右下角，不会挡住 Chrome 正中央的二维码。

        每次调用会**覆盖文案**（用于登录中、下载中等阶段提示，不会叠层）。
        若调用者改了 `anchor`，且旧浮层 anchor 不同，会自动重建一个新窗口贴过去。
        """
        # anchor 不传就沿用当前任务锚点；传了就把任务锚点一起更新（供后续 _on_crawler_log 使用）
        if anchor is None:
            anchor = self._task_overlay_anchor
        else:
            self._task_overlay_anchor = anchor
        x, y, w, h = self._floating_geometry(above=True, anchor=anchor)
        need_rebuild = (
            self._task_overlay is None
            or not self._task_overlay.isVisible()
            or getattr(self._task_overlay, "_anchor", None) != anchor
        )
        if need_rebuild:
            try:
                if self._task_overlay is not None:
                    self._task_overlay.close()
            except Exception:
                pass
            lb = _FloatingLabel(text, duration_ms=-1, mode="task", parent=None, anchor=anchor)
            lb.setAttribute(Qt.WA_DeleteOnClose, False)
            lb.move(x, y)
            lb.resize(w, h)
            lb.show()
            self._task_overlay = lb
        else:
            self._task_overlay.setText(text)
            self._task_overlay.move(x, y)
            self._task_overlay.resize(w, h)
            # 被用户临时/永久隐藏过的浮层，外部更新文案时强制再 show 一下，避免它静默
            if not getattr(self._task_overlay, "_permanent_hidden", False):
                try:
                    self._task_overlay.setWindowOpacity(1.0)
                    self._task_overlay.show()
                    self._task_overlay.raise_()
                except Exception:
                    pass

    def _task_overlay_hide(self):
        if self._task_overlay is not None:
            try:
                self._task_overlay.close()
            except Exception:
                pass
            self._task_overlay = None
        # 任务结束复位锚点 & 阶段状态
        self._task_overlay_anchor = "above_pet"
        self._task_stage = ""

    # ======================== 状态管理 ========================

    def _on_state_changed(self, old_state, new_state):
        """状态变化回调"""
        self._animator.play(new_state)

        # 状态切换后更新窗口大小
        self.setFixedSize(self._label.size())

        if new_state == PetState.WALKING:
            self._walk_timer.start(WALK_INTERVAL)
        else:
            self._walk_timer.stop()

        if new_state == PetState.IDLE:
            self._start_idle()
        else:
            self._idle_timer.stop()

    def _start_idle(self):
        """开始待机倒计时（随机触发行走）"""
        interval = random.randint(IDLE_INTERVAL_MIN, IDLE_INTERVAL_MAX)
        self._idle_timer.start(interval)

    def _on_idle_timeout(self):
        """待机超时，随机进入行走"""
        if self._state_machine.state == PetState.IDLE:
            self._walk_direction = random.choice([1, -1])
            self._state_machine.transition_to(PetState.WALKING)

    def _on_walk(self):
        """行走定时器回调"""
        pos = self.pos()
        new_x = pos.x() + self._walk_direction * WALK_SPEED

        # 边界检测
        screen = QApplication.primaryScreen().geometry()
        if new_x <= 0 or new_x + self.width() >= screen.width():
            self._walk_direction *= -1  # 反向
            new_x = pos.x() + self._walk_direction * WALK_SPEED

        self.move(new_x, pos.y())

        # 随机停止行走
        if random.random() < 0.005:  # 每帧0.5%概率停止
            self._state_machine.transition_to(PetState.IDLE)

    # ======================== 鼠标事件 ========================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.pos()
            self._dragging = False

        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            distance = (event.globalPosition().toPoint() -
                        self._press_pos).manhattanLength()

            if distance > DRAG_THRESHOLD and not self._dragging:
                # 开始拖拽
                self._dragging = True
                self._state_machine.force_transition(PetState.DRAGGING)
                self._animator.play_sound(PetState.DRAGGING)

            if self._dragging:
                self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._dragging:
                # 拖拽结束 → 停音效 → 松开动画 → 待机
                self._animator.stop_sound()
                # 用 force_transition 因为 DRAGGING 不可打断
                self._state_machine.force_transition(PetState.RELEASED)
                # 800ms 后回到待机（RELEASED 可正常转换）
                QTimer.singleShot(800, lambda: (
                    self._state_machine.transition_to(PetState.IDLE)
                ))
            else:
                # 点击反馈（当前 SOUND_MAP 没有 IDLE 的音效，不播）
                # 后续可加 PATTED 状态音效：self._animator.play_sound(PetState.PATTED)
                pass
            self._dragging = False

    # ======================== 右键菜单 ========================

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        menu = QMenu(self)

        action_eat = QAction("吃东西", self)
        action_ask = QAction("求投喂", self)
        action_feed = QAction("喂食", self)

        # ======================================================================
        # 扩展动作（右键直接可点的交互）占位 —— **整块注释掉（COMMENTED OUT）暂不生效**
        #
        # 来源：
        #   · 框架文档 v3 §3.1 "可添加：洗澡、生病、开心 等"
        #   · §4 菜单里原先删掉的「摸头/对话」占位（框架 §4.7 说明："摸头 / 对话 / 更多设置
        #     留到素材到位后按需扩"）
        #   · §2.2 "情绪系统 / 更多食物类型 / 触摸反馈"
        #
        # 启用方式：
        #   1) 先打开 src/pet_state_machine.py 里 PetState 扩展枚举的注释；
        #   2) 打开 src/pet_animator.py 里 _EXT_ASSET_MAP / _EXT_ITEM_IMAGES 的注释；
        #   3) 打开 src/interaction.py 里扩展 start_* 的注释；
        #   4) 最后把下面这一大段解注释，并把 triggered.connect 连到 self._interaction.xxx；
        # 全部用试验素材（试.gif / 试_物品东西.png）暂代，解注释后不会崩。
        # ----------------------------------------------------------------------
        # # 子菜单「情绪 ▶」
        # emotion_menu = menu.addMenu("情绪")
        # action_emotion_happy     = QAction("开心", self)
        # action_emotion_sad       = QAction("委屈/难过", self)
        # action_emotion_sick      = QAction("生病", self)
        # action_emotion_angry     = QAction("生气", self)      # 其实 PetState.ANGRY 已有
        # action_emotion_shy       = QAction("害羞（被送礼物）", self)
        # action_emotion_surprised = QAction("惊讶", self)
        # action_emotion_crying    = QAction("哭泣", self)
        # action_emotion_laughing  = QAction("大笑", self)
        # emotion_menu.addAction(action_emotion_happy)
        # emotion_menu.addAction(action_emotion_sad)
        # emotion_menu.addAction(action_emotion_sick)
        # emotion_menu.addAction(action_emotion_shy)
        # emotion_menu.addAction(action_emotion_surprised)
        # emotion_menu.addAction(action_emotion_crying)
        # emotion_menu.addAction(action_emotion_laughing)
        # # （ANGRY 已经在映射里有，这里留一条占位提醒）
        # # emotion_menu.addAction(action_emotion_angry)
        #
        # # 子菜单「互动 ▶」：框架里原来的摸头 / 对话 占位 加回来
        # inter_menu = menu.addMenu("互动")
        # action_inter_patted  = QAction("摸头", self)        # 框架 §4 里之前说要删的占位，先回到这里当注释
        # action_inter_poked   = QAction("戳一下", self)
        # action_inter_talk    = QAction("对话（占位）", self)  # 对话暂无后端实现，仅占位
        # action_inter_gift    = QAction("送礼物", self)
        # inter_menu.addAction(action_inter_patted)
        # inter_menu.addAction(action_inter_poked)
        # inter_menu.addAction(action_inter_gift)
        # inter_menu.addSeparator()
        # inter_menu.addAction(action_inter_talk)
        #
        # # 子菜单「状态 ▶」：睡觉/打盹/放空等
        # status_menu = menu.addMenu("状态")
        # action_status_sleeping   = QAction("睡觉（深睡）", self)  # PetState.SLEEPING 已存在
        # action_status_napping    = QAction("打盹（浅睡）", self)
        # action_status_stretching = QAction("伸懒腰", self)
        # action_status_yawn       = QAction("打哈欠", self)
        # action_status_zoning     = QAction("放空/发呆", self)
        # action_status_playing    = QAction("玩耍", self)         # PetState.PLAYING 已存在
        # status_menu.addAction(action_status_playing)
        # status_menu.addAction(action_status_sleeping)
        # status_menu.addAction(action_status_napping)
        # status_menu.addAction(action_status_stretching)
        # status_menu.addAction(action_status_yawn)
        # status_menu.addAction(action_status_zoning)
        #
        # # 子菜单「吃喝 ▶」：框架 §2.2 更多食物类型（吃猪蹄/豆腐已经在基础三件里，这里扩展零食饮料）
        # food_menu = menu.addMenu("吃喝")
        # action_food_snack   = QAction("吃零食（冰淇淋）", self)
        # action_food_drink   = QAction("喝奶茶", self)
        # action_food_singing = QAction("唱首歌", self)     # 顺便跟吃喝在同一块里，放麦克风道具
        # food_menu.addAction(action_food_snack)
        # food_menu.addAction(action_food_drink)
        # food_menu.addSeparator()
        # food_menu.addAction(action_food_singing)
        #
        # # 子菜单「彩蛋 ▶」：跳舞 / 跑步 / 看书玩手机（B 站/抖音新视频 / 挂机用）
        # extra_menu2 = menu.addMenu("彩蛋")
        # action_ext_dancing  = QAction("跳舞", self)
        # action_ext_running  = QAction("小跑一下", self)
        # action_ext_reading  = QAction("看书/玩手机（挂机）", self)
        # action_ext_bathing  = QAction("洗澡", self)
        # extra_menu2.addAction(action_ext_dancing)
        # extra_menu2.addAction(action_ext_running)
        # extra_menu2.addAction(action_ext_reading)
        # extra_menu2.addSeparator()
        # extra_menu2.addAction(action_ext_bathing)
        #
        # # —— 占位：上面这些动作的 triggered.connect（素材到位、InteractionManager 里
        # #    start_xxx 解注释后，再把这一段取消注释即可）——
        # # action_emotion_happy.triggered.connect(self._interaction.start_happy)
        # # action_emotion_sad.triggered.connect(self._interaction.start_sad)
        # # action_emotion_sick.triggered.connect(self._interaction.start_sick)
        # # action_emotion_shy.triggered.connect(self._interaction.start_shy_gift)
        # # action_emotion_surprised.triggered.connect(self._interaction.start_surprised)
        # # action_emotion_crying.triggered.connect(self._interaction.start_crying)
        # # action_emotion_laughing.triggered.connect(self._interaction.start_laughing)
        # # action_inter_patted.triggered.connect(self._interaction.start_patted_head)
        # # action_inter_poked.triggered.connect(self._interaction.start_poked)
        # # action_inter_gift.triggered.connect(self._interaction.start_shy_gift)
        # # action_status_napping.triggered.connect(self._interaction.start_napping)
        # # action_status_stretching.triggered.connect(self._interaction.start_stretching)
        # # action_status_yawn.triggered.connect(self._interaction.start_yawn)
        # # action_status_zoning.triggered.connect(self._interaction.start_zoning_out)
        # # action_food_snack.triggered.connect(self._interaction.start_eating_snack)
        # # action_food_drink.triggered.connect(self._interaction.start_drinking)
        # # action_food_singing.triggered.connect(self._interaction.start_singing)
        # # action_ext_dancing.triggered.connect(self._interaction.start_dancing)
        # # action_ext_running.triggered.connect(self._interaction.start_running)
        # # action_ext_reading.triggered.connect(self._interaction.start_reading_phone)
        # # action_ext_bathing.triggered.connect(self._interaction.start_bathing)
        # # （SLEEPING / PLAYING 已经在基础状态机里有，只是还没挂菜单，要不要加菜单另说）
        # ======================================================================

        # 拓展功能子菜单（DLC：爬虫等）
        extras_menu = menu.addMenu("拓展功能")

        # —— B站爬虫
        action_crawl_bili = QAction("爬取B站最新视频", self)
        extras_menu.addAction(action_crawl_bili)

        extras_menu.addSeparator()

        # —— 抖音爬虫（独立子菜单，跟 B站平级，都是拓展能力）
        douyin_menu = extras_menu.addMenu("抖音")
        action_crawl_douyin = QAction("爬取抖音最新视频", self)
        action_douyin_login = QAction("登录/重新登录（扫码）", self)
        action_douyin_logout = QAction("清除登录数据（退出登录）", self)
        douyin_menu.addAction(action_crawl_douyin)
        douyin_menu.addAction(action_douyin_login)
        douyin_menu.addAction(action_douyin_logout)

        extras_menu.addSeparator()

        action_proxy_settings = QAction("代理设置…", self)
        extras_menu.addAction(action_proxy_settings)

        action_clear_privacy = QAction("清除隐私数据…", self)
        action_clear_privacy.setToolTip("一键选择删除本地代理配置 / 抖音 Cookie / 抖音 Chrome 用户资料目录等隐私文件")
        extras_menu.addAction(action_clear_privacy)

        extras_menu.addSeparator()

        action_open_data_dir = QAction("打开 data 目录", self)
        action_open_data_dir.setToolTip(
            "打开程序运行时数据根目录（打包 exe 后与 exe 同级目录下的 data）。\n"
            "里面放有：下载历史 download_history.json、抖音登录数据、以及临时/缓存文件。\n"
            "——爬虫失败时可来此查看 data/tmp 下保留的现场。"
        )
        extras_menu.addAction(action_open_data_dir)

        action_open_output_dir = QAction("打开 output 目录", self)
        action_open_output_dir.setToolTip(
            "打开最终成品输出目录（打包 exe 后与 exe 同级）。\n"
            "抖音、B 站等爬虫下载合并完成后，都会把成品放到这里。"
        )
        extras_menu.addAction(action_open_output_dir)

        # 彩蛋：ihan 粉丝站
        action_ihan = QAction("ihan 粉丝站 ✨", self)

        # ---------- 设置：窗口显示偏好（持久化 settings.json）----------
        settings_menu = menu.addMenu("设置")

        self._action_always_on_top = QAction("窗口置顶", self)
        self._action_always_on_top.setCheckable(True)
        self._action_always_on_top.setChecked(self._app_cfg.always_on_top)
        self._action_always_on_top.setToolTip(
            "打开后，宠物窗口永远压在浏览器/游戏等最上层；\n"
            "关掉后，她会像普通窗口一样被其它窗口盖住。"
        )
        settings_menu.addAction(self._action_always_on_top)

        action_size = QAction("调整宠物大小…", self)
        action_size.setToolTip(
            "调整宠物显示高度（默认 240 px）；\n"
            f"允许范围 {PET_HEIGHT_MIN}~{PET_HEIGHT_MAX} px，物品图自动按 1/3 高度联动。"
        )
        settings_menu.addAction(action_size)

        settings_menu.addSeparator()
        action_reset_size = QAction("恢复默认设置", self)
        action_reset_size.setToolTip(
            f"重置为：窗口置顶=开 / 宠物高度={PET_HEIGHT_DEFAULT} px，并立即写入 data/settings.json。"
        )
        settings_menu.addAction(action_reset_size)

        # 仓库子菜单（关于项目仓库本身的信息、作者链接、彩蛋）
        repo_menu = menu.addMenu("关于此项目")
        action_github = QAction("GitHub", self)
        action_gitee = QAction("Gitee", self)
        repo_menu.addAction(action_github)
        repo_menu.addAction(action_gitee)
        repo_menu.addSeparator()
        repo_menu.addAction(action_ihan)

        menu.addSeparator()
        action_quit = QAction("退出", self)

        menu.addAction(action_eat)
        menu.addAction(action_ask)
        menu.addAction(action_feed)
        menu.addSeparator()
        menu.addMenu(extras_menu)
        menu.addMenu(settings_menu)
        menu.addSeparator()
        menu.addMenu(repo_menu)
        menu.addSeparator()
        menu.addAction(action_quit)

        action_eat.triggered.connect(self._interaction.start_eating)
        action_ask.triggered.connect(self._interaction.start_asking_food)
        action_feed.triggered.connect(self._interaction.start_feeding)
        action_crawl_bili.triggered.connect(self._crawl_bilibili)
        # 抖音三件套：爬取 / 登录 / 清除登录数据
        action_crawl_douyin.triggered.connect(self._crawl_douyin)
        action_douyin_login.triggered.connect(self._douyin_login)
        action_douyin_logout.triggered.connect(self._douyin_logout)
        action_proxy_settings.triggered.connect(self._open_proxy_settings)
        action_clear_privacy.triggered.connect(self._open_clear_privacy)
        action_open_data_dir.triggered.connect(self._open_data_dir)
        action_open_output_dir.triggered.connect(self._open_output_dir)
        # 设置：显示偏好
        self._action_always_on_top.toggled.connect(self._toggle_always_on_top)
        action_size.triggered.connect(self._open_pet_size_settings)
        action_reset_size.triggered.connect(self._reset_app_settings)
        # 关于此项目
        action_github.triggered.connect(self._open_github)
        action_gitee.triggered.connect(self._open_gitee)
        action_ihan.triggered.connect(self._open_ihan)
        action_quit.triggered.connect(self._quit_app)

        menu.exec(pos)

    # ------------------------------------------------------------------ 设置：重置

    def _reset_app_settings(self) -> None:
        """一键恢复默认设置：窗口置顶=开 / 宠物高度=240px。"""
        confirm = QMessageBox.question(
            self,
            "恢复默认设置",
            "确认把显示设置恢复成出厂默认？\n\n"
            "  · 窗口置顶：开\n"
            f"  · 宠物高度：{PET_HEIGHT_DEFAULT} px\n\n"
            "（只影响 settings.json，不会动你的登录数据、下载历史、素材）",
        )
        if confirm != QMessageBox.Yes:
            return

        self._app_cfg = AppConfig().clamp()
        # 1. 应用宠物高度
        from .pet_animator import apply_app_config as _apply_animator_cfg
        _apply_animator_cfg(self._app_cfg)
        # 2. 对当前帧重绘 + 窗口大小 + 位置对齐
        self._animator.apply_sizes_now(self._app_cfg.pet_height, self._app_cfg.item_height)
        label_size = self._label.size()
        self.setFixedSize(label_size)
        # 3. 置顶 flag 按新 cfg 重置（用现有 _toggle 路径，但先强制 setChecked 会触发 toggled）
        if self._action_always_on_top is not None:
            # 注意：blockSignals 临时打断，避免再保存一次 save_app_config（下方统一保存）
            self._action_always_on_top.blockSignals(True)
            self._action_always_on_top.setChecked(self._app_cfg.always_on_top)
            self._action_always_on_top.blockSignals(False)
        visible = self.isVisible()
        old_pos = self.pos()
        flags = self.windowFlags()
        if self._app_cfg.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.move(old_pos)
        if visible:
            self.show()
        # 4. 统一持久化 + 提示
        self._save_app_cfg_and_notice("已恢复默认显示设置")

    def _open_github(self):
        """用系统默认浏览器打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def _open_gitee(self):
        """用系统默认浏览器打开 Gitee 仓库"""
        QDesktopServices.openUrl(QUrl(GITEE_URL))

    def _open_ihan(self):
        """彩蛋：用系统默认浏览器打开王涵粉丝站 ihan.com.cn"""
        QDesktopServices.openUrl(QUrl(IHAN_URL))

    def _open_proxy_settings(self):
        dlg = ProxySettingsDialog(self)
        dlg.exec()

    def _open_clear_privacy(self):
        dlg = ClearPrivacyDialog(self)
        dlg.exec()

    def _open_data_dir(self):
        """在资源管理器里打开 data 根目录（exe 打包后用户依然可以随时查看/清理/找失败现场）。"""
        from .resource_manager import get_data_path, open_in_explorer
        p = get_data_path("")
        ok, err = open_in_explorer(p)
        if not ok:
            QMessageBox.warning(self, "打开失败", f"无法打开 data 目录：\n{p}\n\n原因：{err}")

    def _open_output_dir(self):
        """在资源管理器里打开 output 根目录（最终成品所在）。"""
        from .resource_manager import get_output_path, open_in_explorer
        p = get_output_path("")
        ok, err = open_in_explorer(p)
        if not ok:
            QMessageBox.warning(self, "打开失败", f"无法打开 output 目录：\n{p}\n\n原因：{err}")

    # ======================== 爬虫入口 ========================

    def _crawl_bilibili(self):
        """后台线程执行 B 站最新视频抓取。"""
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            QMessageBox.information(self, "提示", "已有爬虫任务在运行，请稍候再试。")
            return

        self._crawler_worker = CrawlerWorker(
            proxy=CRAWLER_PROXY,
            headless=CRAWLER_HEADLESS,
        )
        self._crawler_worker.log.connect(self._on_crawler_log)
        self._crawler_worker.finished_ok.connect(self._on_crawler_ok)
        self._crawler_worker.failed.connect(self._on_crawler_failed)
        # 无论成功失败，统一先把长任务浮层收掉
        self._crawler_worker.finished_ok.connect(lambda *_: self._task_overlay_hide())
        self._crawler_worker.failed.connect(lambda *_: self._task_overlay_hide())
        self._crawler_worker.start()

        self._task_overlay_show("正在启动 B 站爬虫…")
        self._show_notice("开始爬取 B 站最新视频", duration_ms=1400)

    # ---------- 抖音 ----------

    def _douyin_login(self):
        """在 QThread 里开浏览器引导扫码登录（单一弹窗 + 统一入口收尾）。

        设计：
          * 扫码引导对话框：非模态 show()，不是 modal exec()。
            对话框内部有「确认登录完成」+「取消」按钮；但不依赖这两个按钮也能走通流程。
          * Worker 侧每秒轮询一次：用户在 Chrome 里登录成功（头像出现）后，worker 会自动检测到，
            此时：
              - 立刻关闭正在显示的"扫码引导"对话框
              - 立刻关闭右下角任务浮层
              - 弹出 1 条"登录成功"轻提示（notice，2s 自动关）
              （不再额外弹第二个"登录成功"对话框，避免堆叠）
          * 只有「用户在对话框里自己点了确认」的场景，才额外弹一个确认对话框告诉用户「已成功」。
        """
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            QMessageBox.information(self, "提示", "已有后台任务在运行，请稍候再试。")
            return

        w = DouyinLoginWorker(proxy=CRAWLER_PROXY)
        self._crawler_worker = w
        w.log.connect(self._on_crawler_log)
        w.failed.connect(self._on_crawler_failed)

        # —— 扫码引导对话框的引用：存实例，登录成功自动关闭时方便调 close() ——
        qr_box_ref: list[QMessageBox] = []

        def on_user_action(text: str):
            # 浮层：右下角提示
            self._task_overlay_show(
                "请在弹出的 Chrome 中扫码登录…",
                anchor="screen_bottom_right",
            )
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(
                    ctypes.windll.kernel32.GetConsoleWindow(), 5
                )
            except Exception:
                pass
            # 非模态 show()，不阻塞事件循环
            box = QMessageBox(self)
            box.setWindowTitle("抖音：扫码登录")
            box.setText(text)
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            box.button(QMessageBox.Ok).setText("确认登录完成")
            box.button(QMessageBox.Cancel).setText("取消")
            box.setAttribute(Qt.WA_DeleteOnClose, False)
            box.setModal(False)
            box.show()
            qr_box_ref.append(box)

            def on_clicked(btn):
                if box.button(QMessageBox.Ok) is btn:
                    w.allow_proceed()
                    # 用户手动确认的同时也提示一下正在保存
                    self._task_overlay_show("正在检测登录状态并保存 Cookie…", anchor="screen_bottom_right")
                elif box.button(QMessageBox.Cancel) is btn:
                    # 取消：worker 会在超时后因未检测到登录态 → failed；这里只关 UI
                    box.close()

            box.buttonClicked.connect(on_clicked)

        w.user_action_required.connect(on_user_action)

        def on_ok(trigger: str):
            """登录成功的统一收尾。trigger ∈ {auto, manual, already}"""

            # 1) 关掉"扫码引导"对话框（如果还开着）
            if qr_box_ref:
                for b in qr_box_ref:
                    try:
                        b.close()
                    except Exception:
                        pass
                qr_box_ref.clear()

            # 2) 关掉任务浮层（不再显示「保存 Cookie 中…」等旧文案）
            self._task_overlay_hide()

            # 3) 根据不同触发方式给用户不同反馈
            if trigger == "already":
                # 打开浏览器时就已是登录态：轻提示 1.6s
                self._show_notice("检测到已有登录态，已保存 Cookie。", duration_ms=1600)
            elif trigger == "auto":
                # 自动检测到用户扫完登录成功：轻提示 1.8s，不弹阻塞对话框
                self._show_notice("✅ 已检测到登录成功，Cookie 已保存。", duration_ms=1800)
            elif trigger == "manual":
                # 用户手动点「确认登录完成」：给 1 条非模态确认提示框
                box = QMessageBox(self)
                box.setWindowTitle("抖音登录成功")
                box.setIcon(QMessageBox.Information)
                box.setStandardButtons(QMessageBox.Ok)
                box.setText(
                    "Cookie 已保存到 data/douyin_cookies.(json|txt)\n"
                    "之后爬抖音就不需要再扫码了。过期后再到 拓展功能 → 抖音 → 登录/重新登录 操作一次即可。"
                )
                box.setAttribute(Qt.WA_DeleteOnClose, True)
                box.show()

        w.finished_ok.connect(on_ok)
        w.failed.connect(lambda *_: self._task_overlay_hide())
        # 失败时也把扫码引导对话框关掉，避免用户在失败后还对着空弹窗发呆
        def on_failed(_):
            if qr_box_ref:
                for b in qr_box_ref:
                    try:
                        b.close()
                    except Exception:
                        pass
                qr_box_ref.clear()
        w.failed.connect(on_failed)
        w.start()

        self._task_overlay_show("正在启动抖音浏览器…", anchor="screen_bottom_right")
        self._show_notice("抖音登录引导已启动", duration_ms=1400)

    def _crawl_douyin(self):
        """抖音最新视频抓取：优先用登录态；未登录先引导登录再继续。"""
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            QMessageBox.information(self, "提示", "已有后台任务在运行，请稍候再试。")
            return

        w = DouyinCrawlWorker(
            sec_uid=DOUYIN_USER_HOME,   # 可直接贴完整主页 URL 或 sec_uid，里面会 normalize
            count=3,
            download=True,
            proxy=CRAWLER_PROXY,
        )
        self._crawler_worker = w
        w.log.connect(self._on_crawler_log)
        w.failed.connect(self._on_crawler_failed)

        def on_ok(video):
            """DouyinCrawlWorker 成功的回调：弹 Explorer 选中下载文件 + 非模态提示框。"""
            self._task_overlay_hide()
            try:
                # 下载目录信息从 cover_url 里取（hack，保证不增加新字段）
                dir_hint = None
                if "|DIR|" in (video.cover_url or ""):
                    _, dir_hint = video.cover_url.split("|DIR|", 1)
                target = find_first_file_in_dir(dir_hint) if dir_hint else None
                extra_msg = ""
                if target and Path(target).exists():
                    import subprocess
                    subprocess.Popen(["explorer", "/select,", target])
                    extra_msg = f"\n\n已自动在资源管理器中高亮此文件。"
                elif dir_hint:
                    extra_msg = f"\n\n下载目录：{dir_hint}"
                box = QMessageBox(self)
                box.setWindowTitle("抖音爬取完成")
                box.setIcon(QMessageBox.Information)
                box.setStandardButtons(QMessageBox.Ok)
                box.setText(
                    f"最新作品：{video.desc or video.aweme_id}\n"
                    f"播放页：{video.web_url}{extra_msg}"
                )
                box.setAttribute(Qt.WA_DeleteOnClose, True)
                box.show()
            except Exception:
                box = QMessageBox(self)
                box.setWindowTitle("抖音爬取完成")
                box.setIcon(QMessageBox.Information)
                box.setStandardButtons(QMessageBox.Ok)
                box.setText(
                    f"最新作品：{video.desc or video.aweme_id}\n播放页：{video.web_url}"
                )
                box.setAttribute(Qt.WA_DeleteOnClose, True)
                box.show()

        w.finished_ok.connect(on_ok)
        w.failed.connect(lambda *_: self._task_overlay_hide())
        w.start()
        # 抖音爬取也会先开 Chrome 进个人主页（万一还没登录 / 有滑块验证，二维码/弹窗仍在正中央），
        # 同样先放右下角；等后续日志更新如果用户把浮层关了也不会再跳回头顶。
        self._task_overlay_show("正在启动抖音爬取任务…", anchor="screen_bottom_right")
        self._show_notice("开始爬取抖音最新视频", duration_ms=1400)

    def _douyin_logout(self):
        """一键清除三处抖音登录数据。带二次确认，避免误删。"""
        crawler = DouyinCrawler()
        locs = crawler.login_data_locations()
        desc = DouyinCrawler.LOGIN_LOCATIONS_DESC

        msg = [
            "即将清除抖音账号的以下 3 处登录数据：",
            "",
            f"  1. Profile 目录  → {locs['chrome_profile_dir']}",
            f"      ({desc['chrome_profile_dir']})",
            "",
            f"  2. Cookie JSON   → {locs['cookies_json']}",
            f"      ({desc['cookies_json']})",
            "",
            f"  3. Cookie TXT    → {locs['cookies_netscape']}",
            f"      ({desc['cookies_netscape']})",
            "",
            "清除后需要再次扫码登录才能使用抖音爬取。确定要清除吗？",
        ]

        box = QMessageBox(self)
        box.setWindowTitle("清除抖音登录数据")
        box.setText("\n".join(msg))
        box.setIcon(QMessageBox.Warning)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("确认清除")
        box.button(QMessageBox.Cancel).setText("取消")
        if box.exec() != QMessageBox.Yes:
            return

        removed = crawler.clear_login_data()
        if removed:
            QMessageBox.information(
                self,
                "清除完成",
                "已清除的登录数据：\n\n" + "\n".join(removed),
            )
        else:
            QMessageBox.information(
                self,
                "清除完成",
                "3 处登录数据本来就都不存在（从未登录过 / 已经清除过）。",
            )

    # ---------- 通用日志/结果回调 ----------

    # 阶段 → 浮层文案 的映射表。条目按"流程上出现的先后顺序"排列。
    # 注意：顺序很重要——因为 _task_stage 只能往前走，
    # 排在前面的阶段在日志里重复出现也不会回滚覆盖后面的文案。
    # 匹配规则：key（第一个元素）是"消息里包含哪个子串就命中这个阶段"。
    _CRAWLER_STAGE_RULES: list[tuple[str, str, str]] = [
        # (msg_contains_substr, stage_name, overlay_text)
        # —— 登录 / 浏览器启动阶段 ——
        ("启动浏览器",         "dy_login_browser",  "抖音浏览器启动中…"),
        ("启动抖音浏览器",     "dy_login_browser",  "抖音浏览器启动中…"),
        ("启动抖音爬取任务",   "dy_crawl_browser",  "抖音爬取浏览器启动中…"),
        ("正在启动浏览器",     "dy_login_browser",  "抖音浏览器启动中…"),
        ("页面打开成功",       "dy_login_qr",       "等待扫码登录…"),
        ("浏览器已打开并跳转", "dy_login_qr",       "请在 Chrome 中扫码登录…"),
        ("便携版 Chrome 已在", "dy_login_qr",       "请在 Chrome 中扫码登录…"),
        ("当前已处于登录态",   "dy_login_save",     "已登录，保存 Cookie…"),
        ("检测登录状态并保存 Cookie", "dy_login_save", "保存 Cookie 中…"),
        ("刷新 Cookie",       "dy_crawl_save",     "刷新登录态…"),
        ("登录成功，Cookie 已保存", "dy_login_done",  "✅ 抖音登录成功"),

        # —— 列表爬取阶段 ——
        ("打开个人主页，获取最新视频列表", "dy_crawl_list",  "正在获取视频列表…"),
        ("导航到个人主页",   "dy_crawl_list",     "加载 UP 主个人主页…"),
        ("首屏 document complete", "dy_crawl_list", "等待作品渲染…"),
        ("等待作品 a",        "dy_crawl_list",     "等待作品卡片渲染…"),
        ("解析到卡片",        "dy_crawl_list_done","已解析视频列表…"),
        ("解析后保留的作品",  "dy_crawl_list_done","视频列表就绪"),
        ("作品列表拿到",      "dy_crawl_list_done","✅ 视频列表已取到"),
        ("共获取",            "dy_crawl_list_done","视频列表已获取"),
        ("作品已拿到",        "dy_crawl_list_done","✅ 视频列表就绪"),

        # —— 下载阶段 ——
        ("开始调用 yt-dlp",   "dy_crawl_dl_start", "调用 yt-dlp 下载中…"),
        ("进入下载阶段",      "dy_crawl_dl_start", "yt-dlp 下载中…"),
        ("yt-dlp 会实时",     "dy_crawl_dl_start", "下载中（yt-dlp 实时回显）"),
        ("下载结束",          "dy_crawl_dl_done",  "下载完成"),

        # —— B 站通用阶段 ——
        ("正在启动 B 站爬虫", "bili_start",        "B站爬虫启动中…"),
        ("B 站首页加载完毕",  "bili_ready",        "已进入UP主投稿页"),
        ("爬取第",            "bili_crawl",        "B站爬取稿件中…"),
        ("解析到视频信息",    "bili_done",         "B站视频信息已取到"),
        ("开始调用 yt-dlp 下载", "bili_dl_start",  "B站下载中（yt-dlp）"),
        ("下载完成",          "bili_dl_done",      "✅ B站下载完成"),
    ]

    def _on_crawler_log(self, msg: str):
        """爬虫进度日志：打印到 Terminal，同时按「阶段映射表」同步更新任务浮层。

        关键点：
          * 每个阶段名（如 dy_login_qr）只允许更新一次浮层；
            后续同阶段的 log 只打印不更新浮层，避免旧信息覆盖新信息。
          * 阶段顺序按 STAGE_RULES 里出现的顺序；
            已经走到了后续阶段，再出现的日志不会把浮层拉回早期文案。
        """
        print("[爬虫]", msg)

        # —— 阶段映射：从后往前匹配（越靠后越精确，优先命中）——
        #   例："登录成功，Cookie 已保存"包含"登录"也包含"保存 Cookie"，但我们要取后者。
        matched_stage: str | None = None
        matched_text: str | None = None
        for substr, stage_name, overlay_text in reversed(type(self)._CRAWLER_STAGE_RULES):
            if substr in msg:
                matched_stage = stage_name
                matched_text = overlay_text
                break

        if matched_stage is None or matched_text is None:
            return

        # 同一个阶段重复出现 → 不覆盖浮层
        # （避免"刷新 Cookie…"日志在"保存Cookie中…"后面重复出现导致浮层回滚）
        if matched_stage == self._task_stage:
            return

        self._task_stage = matched_stage
        self._task_overlay_show(matched_text)

    def _on_crawler_ok(self, info):
        """B 站爬虫成功完成：非模态提示 + 资源管理器高亮选中文件（不阻塞 Qt，宠物可拖）。"""
        self._task_overlay_hide()
        try:
            output_path = Path(info.output_path)
            if output_path.exists():
                # 高亮选中这个文件（Windows Explorer）
                import subprocess
                subprocess.Popen(["explorer", "/select,", str(output_path)])
            box = QMessageBox(self)
            box.setWindowTitle("B 站爬取完成")
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok)
            box.setText(f"最新视频：{info.title}\n\n已保存到：\n{info.output_path}")
            box.setAttribute(Qt.WA_DeleteOnClose, True)
            box.show()
        except Exception:
            box = QMessageBox(self)
            box.setWindowTitle("B 站爬取完成")
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok)
            box.setText(f"{info.title}\n输出：{info.output_path}")
            box.setAttribute(Qt.WA_DeleteOnClose, True)
            box.show()

    def _on_crawler_failed(self, err_msg: str):
        """失败弹窗；如果是抖音未登录需要扫码，额外提供一个"现在去登录"按钮。"""
        # 写错误日志到文件（单文件，超过 200KB 自动截断保留最后 100KB）
        self._write_error_log(err_msg)
        need_login = "登录" in err_msg or ("Cookie" in err_msg and "抖音" in err_msg) or "douyin_cookies" in err_msg
        if need_login:
            box = QMessageBox(self)
            box.setWindowTitle("爬虫失败")
            box.setText(err_msg + "\n\n现在要不要立刻去做一次扫码登录？")
            box.setIcon(QMessageBox.Warning)
            btn_now = box.addButton("现在去登录", QMessageBox.AcceptRole)
            btn_log = box.addButton("查看错误日志", QMessageBox.ActionRole)
            btn_later = box.addButton("稍后再说", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is btn_now:
                # 防止被爬虫占用 worker
                if self._crawler_worker is not None and self._crawler_worker.isRunning():
                    self._crawler_worker.quit()
                    self._crawler_worker.wait(2000)
                self._douyin_login()
            elif box.clickedButton() is btn_log:
                from .resource_manager import get_data_path, open_in_explorer
                log_path = get_data_path("crawler_error.log")
                open_in_explorer(log_path, select_file=True)
            return
        # 普通失败弹窗，附带「查看日志」按钮
        box = QMessageBox(self)
        box.setWindowTitle("爬虫失败")
        box.setIcon(QMessageBox.Warning)
        box.setText(err_msg)
        btn_view_log = box.addButton("查看错误日志", QMessageBox.AcceptRole)
        box.addButton("关闭", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is btn_view_log:
            from .resource_manager import get_data_path, open_in_explorer
            log_path = get_data_path("crawler_error.log")
            open_in_explorer(log_path, select_file=True)

    # ======================== 清理 ========================

    def _write_error_log(self, err_msg: str):
        """把爬虫错误追加写入 data/crawler_error.log，超过 200KB 自动截断保留最后 100KB"""
        import datetime
        from .resource_manager import get_data_path
        log_path = get_data_path("crawler_error.log")
        try:
            entry = f"\n{'='*60}\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n{err_msg}\n"
            # 检查文件大小，超过 200KB 就先截断
            if os.path.isfile(log_path) and os.path.getsize(log_path) > 200_000:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                # 只保留最后 100KB
                content = content[-100_000:] if len(content) > 100_000 else content
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(content)
            # 追加新条目
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass  # 写日志失败不能影响主流程

    def _quit_app(self):
        """右键「退出」：关掉所有窗口 + 停线程 + 彻底退出进程"""
        # 先清理物品窗口、动画、爬虫线程（跟 closeEvent 一样）
        self._interaction.cleanup()
        self._animator.stop()
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            self._crawler_worker.quit()
            self._crawler_worker.wait(2000)
        # 关掉所有顶层窗口（物品窗口、浮层等 Tool 窗口）
        app = QApplication.instance()
        if app is not None:
            for w in app.topLevelWidgets():
                if w is not self:
                    w.close()
        # 最后退出 app（不等窗口事件循环）
        QApplication.quit()

    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            self._crawler_worker.quit()
            self._crawler_worker.wait(2000)
        self._interaction.cleanup()
        self._animator.stop()
        event.accept()
