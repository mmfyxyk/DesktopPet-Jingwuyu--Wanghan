"""动画管理模块

根据宠物状态切换动画/图片。
当前使用试验素材：
- 试.gif  → 动画（IDLE/WALKING/EATING 等状态共用）
- 试.png  → 静态图（DRAGGING 状态）
- 试_物品东西.png → 物品图（骨头/豆腐/葡萄汁）
- 试.mp3  → 音效

后期替换正式素材时，只需修改 ASSET_MAP 映射表。

运行时尺寸（宠物高度 / 物品高度）不再硬编码死，
通过 ``apply_app_config(cfg)`` 在启动时/用户改动设置后生效。
"""

from PySide6.QtCore import QObject, QTimer, Signal, QSize, Qt, QUrl
from PySide6.QtGui import QPixmap, QMovie, QImageReader
from PySide6.QtWidgets import QLabel
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .pet_state_machine import PetState
from .resource_manager import get_asset_path


# ======================== 默认显示尺寸（实际值来自 AppConfig，运行时可改） ========================
#
# 保留这些常量作为：
#   1. 用户尚未写入 settings.json 时的兜底默认值（= PET_HEIGHT_DEFAULT / 1:3）
#   2. 老代码外部直接 import PET_HEIGHT 的兼容（不要直接改常量，走 apply_app_config）
#
from .config import PET_HEIGHT_DEFAULT, ITEM_HEIGHT_RATIO

PET_HEIGHT = PET_HEIGHT_DEFAULT     # 运行时覆盖；不要在别处直接改这个值
ITEM_HEIGHT = max(40, int(PET_HEIGHT_DEFAULT * ITEM_HEIGHT_RATIO))   # 同上，联动值


def _runtime_sizes() -> tuple[int, int]:
    """返回 (pet_height, item_height)。优先用运行时 apply 覆盖过的值。"""
    return PET_HEIGHT, ITEM_HEIGHT


def set_runtime_heights(pet_height: int, item_height: int) -> None:
    """设置运行时尺寸（只改内存中的值，不存盘；持久化交给 config.save_app_config）。"""
    global PET_HEIGHT, ITEM_HEIGHT
    PET_HEIGHT = int(pet_height)
    ITEM_HEIGHT = int(item_height)


def apply_app_config(cfg) -> None:
    """把一个 ``AppConfig`` 应用到动画模块（PET_HEIGHT / ITEM_HEIGHT 联动）。

    调用方负责存盘。调用后 animator 的下一次 play() / get_item_pixmap() 就按新尺寸计算。
    """
    from .config import AppConfig
    if isinstance(cfg, AppConfig):
        set_runtime_heights(cfg.pet_height, cfg.item_height)
    else:
        set_runtime_heights(PET_HEIGHT_DEFAULT, max(40, int(PET_HEIGHT_DEFAULT * ITEM_HEIGHT_RATIO)))


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
    自动按当前运行时的 PET_HEIGHT（由 AppConfig 联动）缩放显示尺寸。
    调用 ``apply_app_config`` 后会用新尺寸即时重绘当前显示的帧（配合 replay_current）。
    """

    # 动画播放完毕信号（用于单次播放动画结束后通知）
    animation_finished = Signal(PetState)

    def __init__(self, label: QLabel):
        super().__init__()
        self._label = label
        self._movie = None          # QMovie 引用（避免被 GC 回收）
        self._pixmap = None         # QPixmap 引用（避免被 GC 回收）
        self._current_state: Optional[PetState] = None
        self._player = None         # 音频播放器
        self._audio_output = None

    # ------------------------------------------------------------------ 尺寸联动

    def apply_sizes_now(self, pet_height: int, item_height: int) -> None:
        """即时用新尺寸重绘当前显示内容（不改全局，只对当前这帧/这张图生效）。"""
        if self._current_state is None:
            # 还没开始显示（PetWindow.__init__ 还没调 play），按启动后的默认来就行
            return
        state = self._current_state
        if state not in ASSET_MAP:
            return
        filename, file_type, fps = ASSET_MAP[state]
        asset_path = get_asset_path(filename)
        if file_type == "gif" and self._movie is not None:
            original = _get_image_size(asset_path)
            if original.isValid():
                scaled = _scaled_size(original, pet_height)
                self._movie.setScaledSize(scaled)
                self._label.setFixedSize(scaled)
            else:
                self._label.setFixedSize(QSize(pet_height, pet_height))
        elif file_type == "png" and self._pixmap is not None:
            original = self._pixmap.size()
            if original.height() > 0:
                scaled = _scaled_size(original, pet_height)
                # 重走 PNG 构造路径：从磁盘读原始 pixmap 再缩放（self._pixmap 已经是缩小过的旧值了）
                fresh = QPixmap(asset_path).scaled(
                    scaled,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._pixmap = fresh
                self._label.setFixedSize(scaled)
                self._label.setPixmap(self._pixmap)

    # ------------------------------------------------------------------ 播放

    def play(self, state: PetState):
        """根据状态播放对应动画"""
        if state not in ASSET_MAP:
            return

        filename, file_type, fps = ASSET_MAP[state]
        asset_path = get_asset_path(filename)
        self._current_state = state
        pet_h, _ = _runtime_sizes()

        if file_type == "gif":
            self._play_gif(asset_path, fps, pet_h)
        elif file_type == "png":
            self._play_png(asset_path, pet_h)

    def _play_gif(self, path: str, fps: int, pet_height: int):
        """播放 GIF 动画（自动缩放到 pet_height）"""
        # 停止上一个动画
        if self._movie is not None:
            self._movie.stop()

        self._movie = QMovie(path)
        if fps > 0:
            self._movie.setSpeed(fps * 10)  # QMovie 速度是百分比

        # 获取原始尺寸并缩放
        original = _get_image_size(path)
        if original.isValid():
            scaled = _scaled_size(original, pet_height)
            self._movie.setScaledSize(scaled)
            self._label.setFixedSize(scaled)
        else:
            self._label.setFixedSize(QSize(pet_height, pet_height))

        self._label.setMovie(self._movie)
        self._movie.start()

        # 保存引用避免 GC
        self._pixmap = None

    def _play_png(self, path: str, pet_height: int):
        """显示静态图片（自动缩放到 pet_height）"""
        if self._movie is not None:
            self._movie.stop()
            self._label.setMovie(None)

        self._pixmap = QPixmap(path)
        # 按高度等比缩放
        original = self._pixmap.size()
        if original.height() > 0:
            scaled = _scaled_size(original, pet_height)
            self._pixmap = self._pixmap.scaled(
                scaled,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._label.setFixedSize(scaled)
        else:
            self._label.setFixedSize(QSize(pet_height, pet_height))

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
        """获取缩放后的物品图片（高度 = 当前配置的 ITEM_HEIGHT）"""
        _, item_h = _runtime_sizes()
        path = get_asset_path(ITEM_IMAGE)
        pixmap = QPixmap(path)
        original = pixmap.size()
        if original.height() > 0:
            scaled = _scaled_size(original, item_h)
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
