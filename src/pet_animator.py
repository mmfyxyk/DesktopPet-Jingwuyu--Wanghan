"""动画管理模块

根据宠物状态切换动画/图片。
当前使用试验素材：
- 试.gif  → 动画（IDLE/WALKING/EATING 等状态共用）
- 试.png  → 静态图（DRAGGING 状态）
- 试_物品东西.png → 物品图（骨头/豆腐/葡萄汁）
- 试.mp3  → 音效

后期替换正式素材时，只需修改 ASSET_MAP 映射表。
"""

from PySide6.QtCore import QObject, QTimer, Signal, QSize, Qt, QUrl
from PySide6.QtGui import QPixmap, QMovie, QImageReader
from PySide6.QtWidgets import QLabel
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .pet_state_machine import PetState
from .resource_manager import get_asset_path


# ======================== 可调配置 ========================

# 宠物显示高度（像素），按原始宽高比等比缩放
# 桌面宠物通常 200-300 像素高，后期可随时调整
PET_HEIGHT = 240
# 物品显示高度（像素）
ITEM_HEIGHT = 80


# ======================== 素材映射 ========================

# 状态 → 素材文件映射（后期替换正式素材时改这里）
ASSET_MAP = {
    PetState.IDLE:        ("试.gif", "gif", 10),    # (文件名, 类型, FPS)
    PetState.WALKING:     ("试.gif", "gif", 15),
    PetState.DRAGGING:    ("试.png", "png", 0),
    PetState.RELEASED:    ("试.gif", "gif", 15),
    PetState.EATING:     ("试.gif", "gif", 20),
    PetState.ASKING_FOOD: ("试.gif", "gif", 12),
    PetState.FEEDING:     ("试.gif", "gif", 20),
    PetState.SLEEPING:    ("试.gif", "gif", 5),
    PetState.PLAYING:     ("试.gif", "gif", 15),
    PetState.ANGRY:       ("试.gif", "gif", 12),
}

# 物品素材
ITEM_IMAGE = "试_物品东西.png"
# 音效素材
SOUND_FILE = "试.mp3"


def _get_image_size(path: str) -> QSize:
    """通过 QImageReader 获取图片/GIF 原始尺寸（不加载完整文件）"""
    reader = QImageReader(path)
    return reader.size()


def _scaled_size(original: QSize, target_height: int) -> QSize:
    """按目标高度等比缩放"""
    if original.height() <= 0:
        return QSize(target_height, target_height)
    ratio = target_height / original.height()
    return QSize(int(original.width() * ratio), target_height)


class PetAnimator(QObject):
    """动画管理器

    负责根据状态切换 QLabel 上显示的动画/图片。
    自动按 PET_HEIGHT 缩放显示尺寸。
    """

    # 动画播放完毕信号（用于单次播放动画结束后通知）
    animation_finished = Signal(PetState)

    def __init__(self, label: QLabel):
        super().__init__()
        self._label = label
        self._movie = None          # QMovie 引用（避免被 GC 回收）
        self._pixmap = None         # QPixmap 引用（避免被 GC 回收）
        self._current_state = None
        self._player = None         # 音频播放器
        self._audio_output = None

    def play(self, state: PetState):
        """根据状态播放对应动画"""
        if state not in ASSET_MAP:
            return

        filename, file_type, fps = ASSET_MAP[state]
        asset_path = get_asset_path(filename)
        self._current_state = state

        if file_type == "gif":
            self._play_gif(asset_path, fps)
        elif file_type == "png":
            self._play_png(asset_path)

    def _play_gif(self, path: str, fps: int):
        """播放 GIF 动画（自动缩放到 PET_HEIGHT）"""
        # 停止上一个动画
        if self._movie is not None:
            self._movie.stop()

        self._movie = QMovie(path)
        if fps > 0:
            self._movie.setSpeed(fps * 10)  # QMovie 速度是百分比

        # 获取原始尺寸并缩放
        original = _get_image_size(path)
        if original.isValid():
            scaled = _scaled_size(original, PET_HEIGHT)
            self._movie.setScaledSize(scaled)
            self._label.setFixedSize(scaled)
        else:
            self._label.setFixedSize(QSize(PET_HEIGHT, PET_HEIGHT))

        self._label.setMovie(self._movie)
        self._movie.start()

        # 保存引用避免 GC
        self._pixmap = None

    def _play_png(self, path: str):
        """显示静态图片（自动缩放到 PET_HEIGHT）"""
        if self._movie is not None:
            self._movie.stop()
            self._label.setMovie(None)

        self._pixmap = QPixmap(path)
        # 按高度等比缩放
        original = self._pixmap.size()
        if original.height() > 0:
            scaled = _scaled_size(original, PET_HEIGHT)
            self._pixmap = self._pixmap.scaled(
                scaled,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._label.setFixedSize(scaled)
        else:
            self._label.setFixedSize(QSize(PET_HEIGHT, PET_HEIGHT))

        self._label.setPixmap(self._pixmap)

    def play_sound(self, filename: str = None):
        """播放音效"""
        sound_path = get_asset_path(filename or SOUND_FILE)
        if self._player is None:
            self._player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._player.setAudioOutput(self._audio_output)

        self._player.setSource(QUrl.fromLocalFile(sound_path))
        self._player.play()

    def get_item_pixmap(self) -> QPixmap:
        """获取缩放后的物品图片"""
        path = get_asset_path(ITEM_IMAGE)
        pixmap = QPixmap(path)
        original = pixmap.size()
        if original.height() > 0:
            scaled = _scaled_size(original, ITEM_HEIGHT)
            pixmap = pixmap.scaled(
                scaled,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        return pixmap

    def stop(self):
        """停止当前动画"""
        if self._movie is not None:
            self._movie.stop()
