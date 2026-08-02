"""主窗口模块.

实现框架文档 2.1 节中的透明窗口、窗口置顶、自由拖拽、自动隐藏等基础功能。
窗口无边框、背景全透明，宠物悬浮于桌面之上。

集成状态机（FSM）、动画管理器（PetAnimator）、交互处理器（InteractionHandler）。
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from .interaction import InteractionHandler
from .pet_animator import PetAnimator
from .pet_state_machine import (
    PetState,
    PetStateMachine,
    Trigger,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# 默认宠物尺寸（框架文档 9.1 节建议 128 或 256）
DEFAULT_PET_SIZE = 256

# 行走状态定时器间隔（毫秒）
WALK_INTERVAL_MS = 50
# 行走单步距离（像素）
WALK_STEP_PIXELS = 3
# 随机行走触发间隔范围（秒）—— 框架文档 3.2 节"每隔30秒"
WALK_RANDOM_MIN_S = 20
WALK_RANDOM_MAX_S = 40


class PetWindow(QWidget):
    """宠物主窗口.

    无边框、背景透明、置顶。内部通过 QLabel 显示宠物动画帧。
    """

    def __init__(self) -> None:
        super().__init__()
        self._topmost = True

        # ---------- 核心组件 ----------
        self.fsm = PetStateMachine(initial_state=PetState.IDLE)
        self.animator = PetAnimator(self)
        self.interaction = InteractionHandler(self)

        # ---------- 显示用 Label ----------
        self._label = QLabel(self)
        self._label.setFixedSize(DEFAULT_PET_SIZE, DEFAULT_PET_SIZE)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 保存 pixmap 引用，避免被 GC 回收（框架 9.1）
        self._current_pixmap: QPixmap | None = None

        # ---------- 行走定时器 ----------
        self._walk_timer = QTimer(self)
        self._walk_timer.setInterval(WALK_INTERVAL_MS)
        self._walk_timer.timeout.connect(self._on_walk_tick)

        # 随机触发行走的定时器
        self._random_walk_timer = QTimer(self)
        self._random_walk_timer.setSingleShot(True)
        self._random_walk_timer.timeout.connect(self._trigger_random_walk)

        # 行走方向（1=右，-1=左）
        self._walk_direction = 1

        # ---------- 窗口属性 ----------
        self._setup_window()

        # ---------- 连接状态机回调 ----------
        self.fsm.on_state_changed.append(self._on_state_changed)
        self.animator.animation_finished.connect(self._on_animation_finished)

        # ---------- 启动 ----------
        self.animator.play(self.fsm.current_state)
        self._schedule_next_random_walk()

    # ------------------------------------------------------------------
    # 窗口初始化
    # ------------------------------------------------------------------
    def _setup_window(self) -> None:
        """配置透明无边框置顶窗口（框架 2.1 节）."""
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # 不在任务栏显示
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.setFixedSize(DEFAULT_PET_SIZE, DEFAULT_PET_SIZE)

        # 初始位置：屏幕右下角偏内
        screen = self.screen().availableGeometry()
        self.move(
            screen.right() - DEFAULT_PET_SIZE - 60,
            screen.bottom() - DEFAULT_PET_SIZE - 60,
        )

    # ------------------------------------------------------------------
    # 外部接口
    # ------------------------------------------------------------------
    def set_pixmap(self, pixmap: QPixmap) -> None:
        """设置当前显示的宠物帧."""
        self._current_pixmap = pixmap
        scaled = pixmap.scaled(
            DEFAULT_PET_SIZE,
            DEFAULT_PET_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

    def toggle_topmost(self, topmost: bool | None = None) -> None:
        """切换窗口置顶状态（框架 2.1 节扩展预留）."""
        self._topmost = not self._topmost if topmost is None else topmost
        if self._topmost:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()  # 修改 windowFlags 后需要重新 show

    # ------------------------------------------------------------------
    # 鼠标事件
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.interaction.show_context_menu(event.position().toPoint())
            return
        self.interaction.on_mouse_press(event)

    def mouseMoveEvent(self, event) -> None:
        self.interaction.on_mouse_move(event)

    def mouseReleaseEvent(self, event) -> None:
        self.interaction.on_mouse_release(event)

    # ------------------------------------------------------------------
    # 状态机回调
    # ------------------------------------------------------------------
    def _on_state_changed(self, payload) -> None:
        """状态切换时联动动画与行为."""
        logger.info(
            "状态切换: %s -> %s (触发: %s)",
            payload.old_state.name, payload.new_state.name, payload.trigger.name,
        )
        self.animator.play(payload.new_state)

        # 进入行走状态时启动定时器
        if payload.new_state == PetState.WALKING:
            self._walk_direction = random.choice([-1, 1])
            self._walk_timer.start()
        elif payload.old_state == PetState.WALKING:
            self._walk_timer.stop()

        # 进入待机时重新安排随机行走
        if payload.new_state == PetState.IDLE:
            self._schedule_next_random_walk()
        else:
            self._random_walk_timer.stop()

    def _on_animation_finished(self, state: PetState) -> None:
        """动作型动画播放完毕，触发 ANIMATION_DONE."""
        self.fsm.try_transition(Trigger.ANIMATION_DONE)

    # ------------------------------------------------------------------
    # 行走逻辑
    # ------------------------------------------------------------------
    def _schedule_next_random_walk(self) -> None:
        """安排下一次随机行走（框架 3.2 节：每隔约30秒）."""
        delay_ms = random.randint(
            WALK_RANDOM_MIN_S * 1000, WALK_RANDOM_MAX_S * 1000
        )
        self._random_walk_timer.start(delay_ms)

    def _trigger_random_walk(self) -> None:
        """随机触发行走状态."""
        if self.fsm.current_state == PetState.IDLE:
            self.fsm.try_transition(Trigger.RANDOM_WALK)

    def _on_walk_tick(self) -> None:
        """行走单步：移动窗口，到达边界则回到 IDLE."""
        if self.fsm.current_state != PetState.WALKING:
            self._walk_timer.stop()
            return

        cur = self.pos()
        new_x = cur.x() + self._walk_direction * WALK_STEP_PIXELS
        new_y = cur.y()

        screen = self.screen().availableGeometry()
        # 撞到边界：回到 IDLE（框架 3.2 节 REACHED_BOUNDARY）
        if new_x <= screen.left() or new_x + self.width() >= screen.right():
            self._walk_direction *= -1
            self.fsm.try_transition(Trigger.REACHED_BOUNDARY)
            return

        self.move(new_x, new_y)

        # 随机停止（框架 3.2 节 RANDOM_STOP）
        if random.random() < 0.005:
            self.fsm.try_transition(Trigger.RANDOM_STOP)


__all__ = ["PetWindow", "DEFAULT_PET_SIZE"]
