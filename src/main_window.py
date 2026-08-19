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
        self._crawler_worker: CrawlerWorker | None = None

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
        action_crawl_bili = QAction("爬取B站最新视频", self)
        extras_menu.addAction(action_crawl_bili)
        # 扩展预留：在此 addAction 增加抖音、ihan 等功能入口

        # 仓库子菜单
        repo_menu = menu.addMenu("关于此项目")
        action_github = QAction("GitHub", self)
        action_gitee = QAction("Gitee", self)
        repo_menu.addAction(action_github)
        repo_menu.addAction(action_gitee)

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
        action_github.triggered.connect(self._open_github)
        action_gitee.triggered.connect(self._open_gitee)
        action_quit.triggered.connect(self.close)

        menu.exec(pos)

    def _open_github(self):
        """用系统默认浏览器打开 GitHub 仓库"""
        QDesktopServices.openUrl(QUrl(GITHUB_URL))

    def _open_gitee(self):
        """用系统默认浏览器打开 Gitee 仓库"""
        QDesktopServices.openUrl(QUrl(GITEE_URL))

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
