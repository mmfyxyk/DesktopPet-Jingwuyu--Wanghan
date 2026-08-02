"""交互逻辑模块.

按照框架文档第 4 章交互方式设计实现：
- 4.1 右键菜单
- 4.2 左键点击 vs 拖拽的区分（移动距离阈值 5 像素）
- 4.3 投喂交互流程
- 4.4 吃东西交互流程
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtWidgets import QMenu

from .pet_state_machine import PetState, Trigger

if TYPE_CHECKING:
    from .main_window import PetWindow

logger = logging.getLogger(__name__)

# 框架文档 4.2 节：点击与拖拽的移动距离阈值（像素）
DRAG_THRESHOLD = 5


class InteractionHandler:
    """交互处理器.

    负责处理鼠标事件、右键菜单，并将交互转换为状态机触发条件。
    """

    def __init__(self, window: "PetWindow") -> None:
        self._window = window
        self._fsm = window.fsm
        self._animator = window.animator

        # 拖拽相关状态
        self._press_pos: QPoint | None = None        # 左键按下时的全局位置
        self._drag_origin: QPoint | None = None      # 窗口原始位置
        self._is_dragging = False

        self._setup_context_menu()

    # ------------------------------------------------------------------
    # 右键菜单（框架 4.1 节）
    # ------------------------------------------------------------------
    def _setup_context_menu(self) -> None:
        self._menu = QMenu(self._window)
        self._menu.setStyleSheet(
            "QMenu { background: #fff; border: 1px solid #ccc; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #e0f7ff; }"
        )

        act_eat = QAction("吃东西", self._window)
        act_eat.triggered.connect(
            lambda: self._fsm.try_transition(Trigger.MENU_EAT)
        )
        self._menu.addAction(act_eat)

        act_ask = QAction("求投喂", self._window)
        act_ask.triggered.connect(
            lambda: self._fsm.try_transition(Trigger.MENU_ASK_FOOD)
        )
        self._menu.addAction(act_ask)

        act_feed = QAction("喂食", self._window)
        act_feed.triggered.connect(
            lambda: self._fsm.try_transition(Trigger.MENU_FEED)
        )
        self._menu.addAction(act_feed)

        self._menu.addSeparator()

        # 设置子菜单（框架 4.1 节）
        menu_settings = QMenu("设置", self._window)
        act_topmost = QAction("窗口置顶", self._window)
        act_topmost.setCheckable(True)
        act_topmost.setChecked(True)
        act_topmost.triggered.connect(self._window.toggle_topmost)
        menu_settings.addAction(act_topmost)
        self._menu.addMenu(menu_settings)

        self._menu.addSeparator()

        act_quit = QAction("退出", self._window)
        act_quit.triggered.connect(self._window.close)
        self._menu.addAction(act_quit)

    def show_context_menu(self, pos: QPoint) -> None:
        """在指定位置显示右键菜单."""
        self._menu.exec(self._window.mapToGlobal(pos))

    # ------------------------------------------------------------------
    # 左键交互：点击 vs 拖拽（框架 4.2 节）
    # ------------------------------------------------------------------
    def on_mouse_press(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_pos = event.globalPosition().toPoint()
        self._drag_origin = self._window.pos()
        self._is_dragging = False

    def on_mouse_move(self, event: QMouseEvent) -> None:
        if self._press_pos is None or self._drag_origin is None:
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        global_pos = event.globalPosition().toPoint()
        moved = (global_pos - self._press_pos).manhattanLength()

        if not self._is_dragging and moved >= DRAG_THRESHOLD:
            # 超过阈值，进入拖拽状态
            self._is_dragging = True
            self._fsm.try_transition(Trigger.LEFT_PRESS)

        if self._is_dragging:
            delta = global_pos - self._press_pos
            self._window.move(self._drag_origin + delta)

    def on_mouse_release(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._is_dragging:
            # 拖拽结束
            self._fsm.try_transition(Trigger.LEFT_RELEASE)
        else:
            # 未超过阈值视为点击
            self._fsm.try_transition(Trigger.USER_CLICK)

        self._press_pos = None
        self._drag_origin = None
        self._is_dragging = False


__all__ = ["InteractionHandler", "DRAG_THRESHOLD"]
