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


def _get_gif_original_fps(path: str) -> float:
    """读取 GIF 原始帧率（从第一帧的 delay 推算）。

    QMovie.setSpeed() 只接受"百分比"，100 = 按 GIF 内置 delay 播放。
    要想精确按某个 fps 播，得先知道 GIF 原始 fps，再算百分比。
    返回值：GIF 原始帧率（float），读取失败返回 10.0（兜底）。
    """
    try:
        from PIL import Image
        img = Image.open(path)
        if getattr(img, "n_frames", 1) <= 1:
            return 10.0
        img.seek(0)
        # GIF 每帧 delay 单位是毫秒，1000/delay = fps
        delay_ms = img.info.get("duration", 100)
        if delay_ms <= 0:
            return 10.0
        return 1000.0 / delay_ms
    except Exception:
        return 10.0


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

# 状态 → 素材文件映射（正式素材，目录 assets/WangHan/JingWuyu/）
ASSET_MAP = {
    PetState.IDLE:          ("WangHan/JingWuyu/idle/IDLE_净无欲全身像.gif", "gif", 30),
    PetState.WALKING_LEFT:  ("WangHan/JingWuyu/walking/left_walking.gif", "gif", 30),
    PetState.WALKING_RIGHT: ("WangHan/JingWuyu/walking/right_walking.gif", "gif", 30),
    PetState.DRAGGING:      ("WangHan/JingWuyu/dragging/dragging1.gif", "gif", 30),
    PetState.DRAGGING_2:    ("WangHan/JingWuyu/dragging/dragging2.gif", "gif", 30),
    PetState.RELEASED:      ("WangHan/JingWuyu/released/released.gif", "gif", 30),
    PetState.EATING:        ("WangHan/JingWuyu/eating/eating1.gif", "gif", 30),
    PetState.EATING_2:      ("WangHan/JingWuyu/eating/eating2.gif", "gif", 30),
    PetState.ASKING:        ("WangHan/JingWuyu/asking/asking.gif", "gif", 30),
    PetState.ASKING_FOOD:   ("WangHan/JingWuyu/asking_food/asking_food.gif", "gif", 30),
    PetState.FEEDING:       ("WangHan/JingWuyu/feeding/feeding.gif", "gif", 30),
    PetState.KISS:          ("WangHan/JingWuyu/kiss/kiss.gif", "gif", 30),
    PetState.KIDDING:       ("WangHan/JingWuyu/kidding/kidding.gif", "gif", 30),
    PetState.SHOWING:       ("WangHan/JingWuyu/showing/showing.gif", "gif", 30),
}

# 音效映射：按状态取对应音效（没列的状态不播音效）
SOUND_MAP = {
    PetState.DRAGGING:      "WangHan/JingWuyu/dragging/dragging1.mp3",
    PetState.RELEASED:      "WangHan/JingWuyu/released/released.mp3",
    PetState.EATING:        "WangHan/JingWuyu/eating/eating1.mp3",
    PetState.EATING_2:      "WangHan/JingWuyu/eating/eating2.mp3",
    PetState.ASKING:        "WangHan/JingWuyu/asking/asking.mp3",
    PetState.ASKING_FOOD:   "WangHan/JingWuyu/asking_food/asking_food.mp3",
    PetState.FEEDING:       "WangHan/JingWuyu/feeding/feeding.mp3",
    PetState.KIDDING:       "WangHan/JingWuyu/kidding/kidding.mp3",
    PetState.SHOWING:       "WangHan/JingWuyu/showing/showing.mp3",
}

# 物品图映射：按状态取对应物品图（没列的状态不掉物品）
ITEM_MAP = {
    PetState.EATING:        "WangHan/JingWuyu/items/猪蹄.png",
    PetState.ASKING_FOOD:   "WangHan/JingWuyu/items/葡萄汁.png",
    PetState.FEEDING:       "WangHan/JingWuyu/items/豆腐.png",
}



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

        # 音频播放器：在 __init__ 里就创建并预热，避免第一次 play() 时
        # 音频设备还没初始化导致没声音（打包后首次运行尤其明显）
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(0.8)

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
        """根据状态播放对应动画（循环播放，用于 IDLE/WALKING 等挂机状态）"""
        self._play(state, one_shot=False)

    def play_one_shot(self, state: PetState):
        """播放一次动画（播完自动发 animation_finished 信号，用于 EATING/FEEDING 等一次性动作）"""
        self._play(state, one_shot=True)

    def _play(self, state: PetState, one_shot: bool):
        if state not in ASSET_MAP:
            return
        filename, file_type, fps = ASSET_MAP[state]
        asset_path = get_asset_path(filename)
        self._current_state = state
        pet_h, _ = _runtime_sizes()

        if file_type == "gif":
            self._play_gif(asset_path, fps, pet_h, one_shot=one_shot)
        elif file_type == "png":
            self._play_png(asset_path, pet_h)

    def _play_gif(self, path: str, fps: int, pet_height: int, one_shot: bool = False):
        """播放 GIF 动画（自动缩放到 pet_height）

        Args:
            path: GIF 文件路径
            fps: 期望播放帧率（tuple 里写的那个）
            pet_height: 宠物目标高度
            one_shot: True = 只播一轮后发 animation_finished 信号
                      False = 循环播放（IDLE/WALKING 等挂机状态）
        """
        # 停止上一个动画
        if self._movie is not None:
            self._movie.stop()
            try:
                self._movie.frameChanged.disconnect()
            except Exception:
                pass

        self._movie = QMovie(path)
        if one_shot:
            # PySide6 QMovie 没有 setLoopCount，用 frameChanged 监听最后一帧
            total_frames = self._movie.frameCount()
            if total_frames > 0:
                self._movie.frameChanged.connect(
                    lambda frame_num: self._on_one_shot_frame(frame_num, total_frames)
                )
            else:
                # frameCount() 返回 0（某些 GIF），兜底用 QTimer 按 fps 估算时长
                original_fps = _get_gif_original_fps(path)
                # 用 PIL 拿真实帧数
                try:
                    from PIL import Image as _PILImage
                    _img = _PILImage.open(path)
                    total_frames = getattr(_img, "n_frames", 1)
                except Exception:
                    total_frames = 1
                duration_ms = int(total_frames / max(fps, 1) * 1000)
                QTimer.singleShot(duration_ms, lambda: self.animation_finished.emit(self._current_state))

        if fps > 0:
            # 读取 GIF 原始帧率，按 tuple 里指定的 fps 精确调速
            # setSpeed(百分比)：100 = 原始速度
            # 百分比 = (期望fps / 原始fps) * 100
            original_fps = _get_gif_original_fps(path)
            speed_percent = int((fps / original_fps) * 100)
            self._movie.setSpeed(speed_percent)

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

    def _on_one_shot_frame(self, frame_num: int, total_frames: int):
        """一次性动画：播到最后一帧时停掉并发信号"""
        if frame_num >= total_frames - 1:
            self._movie.stop()
            self.animation_finished.emit(self._current_state)

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

    def play_sound(self, state=None):
        """播放音效。传 state 查 SOUND_MAP，在表里就播，不在表里就不播"""
        if state is None or state not in SOUND_MAP:
            return
        sound_path = get_asset_path(SOUND_MAP[state])
        # _player 在 __init__ 里就创建好了，这里直接 setSource + play
        self._player.setSource(QUrl.fromLocalFile(sound_path))
        self._player.play()

    def stop_sound(self):
        """立即停止当前音效（拖拽松手时调，音效讲究及时性）"""
        if self._player is not None:
            self._player.stop()

    def get_item_pixmap(self, state=None):
        """获取缩放后的物品图片。传 state 查 ITEM_MAP，在表里就取对应图，不在表里返回 None"""
        if state is None or state not in ITEM_MAP:
            return None
        _, item_h = _runtime_sizes()
        path = get_asset_path(ITEM_MAP[state])
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
