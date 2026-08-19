"""主窗口模块

透明无边框窗口，宠物悬浮于桌面之上。
集成状态机、动画管理器、交互管理器。
实现拖拽、右键菜单、行走等核心功能。
"""

import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPoint, QUrl
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QApplication, QMessageBox
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
CRAWLER_PROXY: str | None = None
# 爬虫：是否无头模式（True 不弹浏览器窗口，运行快；False 会弹出一个最小化的 Chrome）
CRAWLER_HEADLESS: bool = False


class PetWindow(QWidget):
    """宠物主窗口"""

    def __init__(self):
        super().__init__()

        # 窗口设置：无边框、透明背景、置顶
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 用于显示动画的 Label
        self._label = QLabel(self)

        # 核心组件
        self._state_machine = StateMachine(PetState.IDLE)
        self._animator = PetAnimator(self._label)
        self._interaction = InteractionManager(
            self._state_machine, self._animator, self
        )

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

        # 初始化
        self._init_ui()
        self._start_idle()

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

            if self._dragging:
                self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._dragging:
                # 拖拽结束 → 松开动画 → 待机
                # 用 force_transition 因为 DRAGGING 不可打断
                self._state_machine.force_transition(PetState.RELEASED)
                # 800ms 后回到待机（RELEASED 可正常转换）
                QTimer.singleShot(800, lambda: (
                    self._state_machine.transition_to(PetState.IDLE)
                ))
            else:
                # 点击 → 播放音效作为反馈
                self._animator.play_sound()
            self._dragging = False

    # ======================== 右键菜单 ========================

    def _show_context_menu(self, pos):
        """显示右键菜单"""
        menu = QMenu(self)

        action_eat = QAction("吃东西", self)
        action_ask = QAction("求投喂", self)
        action_feed = QAction("喂食", self)

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

        # 彩蛋：ihan 粉丝站
        action_ihan = QAction("ihan 粉丝站 ✨", self)

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
        # 关于此项目
        action_github.triggered.connect(self._open_github)
        action_gitee.triggered.connect(self._open_gitee)
        action_ihan.triggered.connect(self._open_ihan)
        action_quit.triggered.connect(self.close)

        menu.exec(pos)

    def _open_github(self):
        """用系统默认浏览器打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def _open_gitee(self):
        """用系统默认浏览器打开 Gitee 仓库"""
        QDesktopServices.openUrl(QUrl(GITEE_URL))

    def _open_ihan(self):
        """彩蛋：用系统默认浏览器打开王涵粉丝站 ihan.com.cn"""
        QDesktopServices.openUrl(QUrl(IHAN_URL))

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
        self._crawler_worker.start()

        # 弹一个"开始爬取"的轻提示
        self._show_notice("开始爬取B站最新视频，请稍候……")

    # ---------- 抖音 ----------

    def _douyin_login(self):
        """在 QThread 里开浏览器引导扫码登录（GUI 弹窗提醒，不依赖终端）。"""
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            QMessageBox.information(self, "提示", "已有后台任务在运行，请稍候再试。")
            return

        w = DouyinLoginWorker(proxy=CRAWLER_PROXY)
        self._crawler_worker = w
        w.log.connect(self._on_crawler_log)
        w.failed.connect(self._on_crawler_failed)

        # 用户扫码完成后，UI 弹"我已登录"对话框；点击确定后 allow_proceed() 让线程继续
        def on_user_action(text: str):
            # 把浏览器恢复到前台，让用户能看到二维码
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(
                    ctypes.windll.kernel32.GetConsoleWindow(), 5
                )
            except Exception:
                pass
            box = QMessageBox(self)
            box.setWindowTitle("抖音：扫码登录")
            box.setText(text)
            box.setIcon(QMessageBox.Information)
            box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            box.button(QMessageBox.Ok).setText("确认登录完成")
            box.button(QMessageBox.Cancel).setText("取消")
            if box.exec() == QMessageBox.Ok:
                w.allow_proceed()

        w.user_action_required.connect(on_user_action)

        def ok():
            QMessageBox.information(
                self,
                "抖音登录成功",
                "Cookie 已保存到 data/douyin_cookies.(json|txt)\n"
                "之后爬抖音就不需要再扫码了。过期后再到 拓展功能 → 抖音 → 登录/重新登录 操作一次即可。",
            )

        w.finished_ok.connect(ok)
        w.start()
        self._show_notice("抖音登录引导启动，请按提示在浏览器中扫码。")

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
            """DouyinCrawlWorker 成功的回调：弹 Explorer 选中下载文件 + 弹窗。"""
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
                QMessageBox.information(
                    self,
                    "抖音爬取完成",
                    f"最新作品：{video.desc or video.aweme_id}\n"
                    f"播放页：{video.web_url}{extra_msg}",
                )
            except Exception as e:
                QMessageBox.information(
                    self,
                    "抖音爬取完成",
                    f"最新作品：{video.desc or video.aweme_id}\n播放页：{video.web_url}",
                )

        w.finished_ok.connect(on_ok)
        w.start()
        self._show_notice("开始爬取抖音最新视频，请稍候……")

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

    def _on_crawler_log(self, msg: str):
        """爬虫进度日志。目前仅打印，后期可接状态栏或气泡。"""
        print("[爬虫]", msg)

    def _on_crawler_ok(self, info):
        """爬虫成功完成：用系统默认文件管理器打开输出位置 + 弹窗提示。"""
        try:
            output_path = Path(info.output_path)
            if output_path.exists():
                # 高亮选中这个文件（Windows Explorer）
                import subprocess
                subprocess.Popen(["explorer", "/select,", str(output_path)])
            QMessageBox.information(
                self,
                "爬取完成",
                f"最新视频：{info.title}\n\n已保存到：\n{info.output_path}",
            )
        except Exception as e:
            QMessageBox.information(self, "爬取完成", f"{info.title}\n输出：{info.output_path}")

    def _on_crawler_failed(self, err_msg: str):
        """失败弹窗；如果是抖音未登录需要扫码，额外提供一个"现在去登录"按钮。"""
        need_login = "登录" in err_msg or ("Cookie" in err_msg and "抖音" in err_msg) or "douyin_cookies" in err_msg
        if need_login:
            box = QMessageBox(self)
            box.setWindowTitle("爬虫失败")
            box.setText(err_msg + "\n\n现在要不要立刻去做一次扫码登录？")
            box.setIcon(QMessageBox.Warning)
            btn_now = box.addButton("现在去登录", QMessageBox.AcceptRole)
            btn_later = box.addButton("稍后再说", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is btn_now:
                # 防止被爬虫占用 worker
                if self._crawler_worker is not None and self._crawler_worker.isRunning():
                    self._crawler_worker.quit()
                    self._crawler_worker.wait(2000)
                self._douyin_login()
            return
        QMessageBox.warning(self, "爬虫失败", err_msg)

    def _show_notice(self, text: str):
        """非模态、自动关闭的轻提示。当前用 QMessageBox.information，后期可换成气泡。"""
        # 用 Qt.Popup 属性让它不阻塞，用户点一下或点别处即关
        box = QMessageBox(self)
        box.setWindowTitle("提示")
        box.setText(text)
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.NoButton)
        box.setWindowFlags(box.windowFlags() | Qt.Popup | Qt.FramelessWindowHint)
        # 1.2 秒自动关
        QTimer.singleShot(1200, box.close)
        # 放在宠物窗口上方
        box.move(self.x() + 10, self.y() - 60)
        box.show()

    # ======================== 清理 ========================

    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        if self._crawler_worker is not None and self._crawler_worker.isRunning():
            self._crawler_worker.quit()
            self._crawler_worker.wait(2000)
        self._interaction.cleanup()
        self._animator.stop()
        event.accept()
