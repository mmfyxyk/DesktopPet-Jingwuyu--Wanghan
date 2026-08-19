"""交互逻辑模块

管理吃东西、求投喂、喂食等交互流程。
物品图片使用独立的透明窗口显示，可被用户拖拽。
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QLabel

from .pet_state_machine import PetState


class ItemWindow(QWidget):
    """物品窗口 - 显示物品图片的透明小窗口，支持拖拽"""

    # 物品被点击信号
    item_clicked = Signal(str)

    def __init__(self, item_name: str, pixmap, parent_pos=None, parent=None):
        super().__init__(parent)
        self._item_name = item_name
        self._dragging = False
        self._drag_offset = None

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._label = QLabel(self)
        # 使用传入的已缩放物品图片
        self._pixmap = pixmap
        self._label.setPixmap(self._pixmap)
        self._label.setFixedSize(self._pixmap.size())
        self.setFixedSize(self._pixmap.size())

        # 在宠物附近显示
        if parent_pos:
            self.move(parent_pos.x() + 80, parent_pos.y() + 20)

    @property
    def item_name(self):
        return self._item_name

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_offset:
            distance = (event.globalPosition().toPoint() -
                        self.pos() - self._drag_offset).manhattanLength()
            if distance > 5:
                self._dragging = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._dragging:
                # 点击 - 发出信号
                self.item_clicked.emit(self._item_name)
            self._drag_offset = None

    def auto_hide(self, delay_ms: int = 5000):
        """延迟自动隐藏"""
        QTimer.singleShot(delay_ms, self.close)


class InteractionManager:
    """交互管理器

    管理吃东西、求投喂、喂食的完整流程。
    由 PetWindow 调用，操作状态机和生成物品。
    """

    def __init__(self, state_machine, animator, pet_window):
        """
        :param state_machine: StateMachine 实例
        :param animator: PetAnimator 实例
        :param pet_window: PetWindow 实例（用于获取位置等）
        """
        self.sm = state_machine
        self.animator = animator
        self.pet_window = pet_window
        self._active_items = []  # 当前活跃的物品窗口列表

    def start_eating(self):
        """吃东西流程：播放动画 → 生成骨头 → 回到待机"""
        if not self.sm.transition_to(PetState.EATING):
            return
        self.animator.play(PetState.EATING)
        self.animator.play_sound()

        # 播放一段时间后生成骨头
        QTimer.singleShot(3000, self._spawn_bone)

    def _spawn_bone(self):
        """生成骨头物品"""
        pixmap = self.animator.get_item_pixmap()
        item = ItemWindow("骨头", pixmap, self.pet_window.pos())
        item.show()
        item.auto_hide(5000)
        self._active_items.append(item)

        # 回到待机
        self.sm.transition_to(PetState.IDLE)
        self.animator.play(PetState.IDLE)

    def start_asking_food(self):
        """求投喂流程：进入求投喂状态 → 生成葡萄汁 → 等待用户投喂"""
        if not self.sm.transition_to(PetState.ASKING_FOOD):
            return
        self.animator.play(PetState.ASKING_FOOD)

        # 生成葡萄汁物品（可拖拽到宠物身上）
        pixmap = self.animator.get_item_pixmap()
        item = ItemWindow("葡萄汁", pixmap, self.pet_window.pos())
        item.item_clicked.connect(self._on_food_given)
        item.show()
        self._active_items.append(item)

        # 10秒超时未投喂则回到待机
        self._ask_timer = QTimer.singleShot(10000, self._on_ask_timeout)

    def _on_food_given(self, item_name):
        """用户点击/拖拽葡萄汁到宠物身上 → 进入喂食"""
        # 关闭葡萄汁物品
        for item in self._active_items[:]:
            if item.item_name == "葡萄汁":
                item.close()
                self._active_items.remove(item)

        self.sm.transition_to(PetState.FEEDING)
        self.animator.play(PetState.FEEDING)

        # 播放一段时间后生成豆腐
        QTimer.singleShot(3000, self._spawn_tofu)

    def _spawn_tofu(self):
        """生成豆腐物品"""
        pixmap = self.animator.get_item_pixmap()
        item = ItemWindow("豆腐", pixmap, self.pet_window.pos())
        item.show()
        item.auto_hide(5000)
        self._active_items.append(item)

        self.sm.transition_to(PetState.IDLE)
        self.animator.play(PetState.IDLE)

    def _on_ask_timeout(self):
        """求投喂超时，回到待机"""
        if self.sm.state == PetState.ASKING_FOOD:
            # 关闭葡萄汁
            for item in self._active_items[:]:
                if item.item_name == "葡萄汁":
                    item.close()
                    self._active_items.remove(item)

            self.sm.transition_to(PetState.IDLE)
            self.animator.play(PetState.IDLE)

    def start_feeding(self):
        """喂食流程：喂用户豆腐，给用户豆腐图片"""
        if not self.sm.transition_to(PetState.FEEDING):
            return
        self.animator.play(PetState.FEEDING)

        QTimer.singleShot(3000, self._spawn_tofu)

    def cleanup(self):
        """清理所有活跃物品"""
        for item in self._active_items:
            item.close()
        self._active_items.clear()
