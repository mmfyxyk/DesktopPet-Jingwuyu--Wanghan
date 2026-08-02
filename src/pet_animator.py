"""动画管理模块.

负责按状态加载并播放对应的动画帧。
按照框架文档 3.3 节动画帧映射表实现。

注意：QPixmap/QImage 对象必须保存为实例属性，避免被 Python GC 回收
导致 Qt 侧资源被释放而无法显示（框架文档 9.1 节注意事项）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from .pet_state_machine import (
    STATE_ANIMATION_CONFIG,
    STATE_ASSETS_DIR,
    PetState,
)
from .resource_manager import get_assets_dir

if TYPE_CHECKING:
    from .main_window import PetWindow

logger = logging.getLogger(__name__)


class PetAnimator(QObject):
    """宠物动画管理器.

    根据当前状态加载对应目录下的 PNG 帧并按设定 FPS 循环播放。
    单帧状态（如 DRAGGING）只显示一张静态图片。
    """

    # 动画播放完毕信号（用于触发 ANIMATION_DONE 状态转换）
    animation_finished = Signal(PetState)

    def __init__(self, window: "PetWindow") -> None:
        super().__init__(window)
        self._window = window
        self._current_state: PetState | None = None
        self._frames: list[QPixmap] = []   # 保持引用避免 GC（框架 9.1）
        self._frame_index = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._loop = True  # 是否循环播放；非循环播放完毕后发 animation_finished

    @property
    def current_state(self) -> PetState | None:
        return self._current_state

    def play(self, state: PetState, loop: bool | None = None) -> None:
        """切换到指定状态的动画.

        Args:
            state: 目标状态。
            loop: 是否循环播放。None 表示按状态自动判断
                  （单帧状态循环，多帧待机/行走等循环，动画型状态不循环）。
        """
        if state == self._current_state and self._frames:
            return

        frames, fps = self._load_frames(state)
        self._frames = frames
        self._frame_index = 0
        self._current_state = state
        self._loop = self._decide_loop(state) if loop is None else loop

        if not frames:
            logger.warning("状态 %s 未加载到任何动画帧", state.name)
            self._timer.stop()
            return

        # 显示第一帧
        self._show_current_frame()

        # 单帧状态：不启动定时器
        if len(frames) <= 1:
            self._timer.stop()
            if not self._loop:
                self.animation_finished.emit(state)
            return

        interval = int(1000 / fps) if fps > 0 else 100
        self._timer.start(interval)

    def stop(self) -> None:
        """停止动画."""
        self._timer.stop()
        self._frames = []
        self._frame_index = 0
        self._current_state = None

    def _decide_loop(self, state: PetState) -> bool:
        """根据状态决定是否循环播放.

        待机/行走/睡觉等持续状态循环播放；
        吃东西/喂食/松开等动作型状态播放一次后触发状态转换。
        """
        return state in {
            PetState.IDLE,
            PetState.WALKING,
            PetState.SLEEPING,
            PetState.PLAYING,
            PetState.ANGRY,
            PetState.ASKING_FOOD,
            PetState.DRAGGING,
        }

    def _load_frames(self, state: PetState) -> tuple[list[QPixmap], int]:
        """加载指定状态的所有动画帧.

        Returns:
            (帧列表, 帧率)
        """
        expected_count, fps = STATE_ANIMATION_CONFIG.get(state, (0, 10))
        dir_name = STATE_ASSETS_DIR.get(state, state.name.lower())
        frames_dir = get_assets_dir(dir_name)

        if not frames_dir.exists():
            logger.warning("动画帧目录不存在: %s", frames_dir)
            return [], fps

        # 按文件名排序加载 PNG
        frame_files = sorted(frames_dir.glob("*.png"))
        if not frame_files:
            # 兼容其他常见扩展名
            frame_files = sorted(
                p for p in frames_dir.iterdir()
                if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
            )

        if not frame_files:
            logger.warning("状态 %s 的动画帧目录为空: %s", state.name, frames_dir)
            return [], fps

        frames: list[QPixmap] = []
        for fp in frame_files:
            pix = QPixmap(str(fp))
            if pix.isNull():
                logger.warning("无法加载图片: %s", fp)
                continue
            frames.append(pix)

        if expected_count and len(frames) != expected_count:
            logger.info(
                "状态 %s 帧数 %d 与预期 %d 不一致",
                state.name, len(frames), expected_count,
            )

        return frames, fps

    def _show_current_frame(self) -> None:
        if not self._frames:
            return
        idx = self._frame_index % len(self._frames)
        self._window.set_pixmap(self._frames[idx])

    def _on_timeout(self) -> None:
        if not self._frames:
            return
        self._frame_index += 1
        if self._frame_index >= len(self._frames):
            if self._loop:
                self._frame_index = 0
            else:
                # 非循环动画播放完毕
                self._timer.stop()
                state = self._current_state
                self._frame_index = len(self._frames) - 1
                self._show_current_frame()
                if state is not None:
                    self.animation_finished.emit(state)
                return
        self._show_current_frame()


__all__ = ["PetAnimator"]
