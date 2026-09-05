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

    # ==========================================================================
    # 扩展交互动作占位（框架 v3 §2.2 情绪系统 / 更多食物类型 / 触摸反馈）
    # —— 新的代码块，**当前整块注释掉（COMMENTED OUT）**，暂不生效 ——
    # 所有需要显示动画的地方都直接调 self.animator.play(对应PetState)，
    # 由于 animator 里的扩展 ASSET_MAP 已用「试.gif / 试_物品东西.png」暂代，
    # 解除下面注释后就算没有正式素材也不会崩，会显示试验素材。
    # --------------------------------------------------------------------------
    # def _spawn_item_by_key(self, item_key: str, duration_ms: int = 5000):
    #     """扩展物品占位：统一用 _EXT_ITEM_IMAGES[item_key] 作为素材（暂代=试_物品东西.png）。
    #
    #     启用步骤（和 pet_animator.py 配套）：
    #       1. 打开 animator 里 _EXT_ITEM_IMAGES 的注释；
    #       2. 这里再实现"按 key 拿不同 pixmap"（animator 里再加一个
    #          get_ext_item_pixmap(item_key) 就行，目前先用统一 get_item_pixmap 暂代）。
    #     """
    #     pixmap = self.animator.get_item_pixmap()   # 试验素材暂代：一张通用图
    #     item = ItemWindow(item_key, pixmap, self.pet_window.pos())
    #     item.show()
    #     item.auto_hide(duration_ms)
    #     self._active_items.append(item)
    #
    # # —— 情绪 / 表情类（只切状态 + 播放动画，不生产物品）——
    # def start_happy(self):        # 开心
    #     if not self.sm.transition_to(PetState.HAPPY): return
    #     self.animator.play(PetState.HAPPY)
    #     QTimer.singleShot(3000, lambda: (self.sm.transition_to(PetState.IDLE), self.animator.play(PetState.IDLE)))
    #
    # def start_sad(self):          # 委屈/难过
    #     if not self.sm.transition_to(PetState.SAD): return
    #     self.animator.play(PetState.SAD)
    #     # 彩蛋：掉一张纸巾 🧻
    #     QTimer.singleShot(1500, lambda: self._spawn_item_by_key("tissue"))
    #
    # def start_sick(self):         # 生病
    #     if not self.sm.transition_to(PetState.SICK): return
    #     self.animator.play(PetState.SICK)
    #     QTimer.singleShot(1500, lambda: self._spawn_item_by_key("thermometer"))
    #
    # def start_bathing(self):      # 洗澡
    #     if not self.sm.transition_to(PetState.BATHING): return
    #     self.animator.play(PetState.BATHING)
    #     QTimer.singleShot(2000, lambda: self._spawn_item_by_key("soap_bubble"))
    #
    # def start_patted_head(self):   # 被摸头（框架里原来的摸头占位，§4 v3 说明曾删掉）
    #     if not self.sm.transition_to(PetState.PATTED): return
    #     self.animator.play(PetState.PATTED)
    #     QTimer.singleShot(1800, lambda: (self.sm.transition_to(PetState.HAPPY), self.animator.play(PetState.HAPPY)))
    #
    # def start_poked(self):        # 被戳
    #     if not self.sm.transition_to(PetState.POKED): return
    #     self.animator.play(PetState.POKED)
    #     QTimer.singleShot(1200, lambda: (self.sm.transition_to(PetState.ANGRY), self.animator.play(PetState.ANGRY)))
    #
    # def start_shy_gift(self):     # 被送礼物 → 害羞（§2.2 可扩展更多投喂物品）
    #     if not self.sm.transition_to(PetState.SHY): return
    #     self.animator.play(PetState.SHY)
    #     self._spawn_item_by_key("gift_box")
    #
    # def start_surprised(self):    # 惊讶
    #     if not self.sm.transition_to(PetState.SURPRISED): return
    #     self.animator.play(PetState.SURPRISED)
    #
    # def start_yawn(self):         # 打哈欠（SLEEPING → IDLE 过渡）
    #     if not self.sm.transition_to(PetState.YAWN): return
    #     self.animator.play(PetState.YAWN)
    #     QTimer.singleShot(2500, lambda: (self.sm.transition_to(PetState.IDLE), self.animator.play(PetState.IDLE)))
    #
    # def start_drinking(self):     # 喝奶茶（框架 §2.2 更多投喂物品）
    #     if not self.sm.transition_to(PetState.DRINKING): return
    #     self.animator.play(PetState.DRINKING)
    #     QTimer.singleShot(2500, lambda: self._spawn_item_by_key("milk_tea"))
    #
    # def start_singing(self):      # 唱歌（语音反馈）
    #     if not self.sm.transition_to(PetState.SINGING): return
    #     self.animator.play(PetState.SINGING)
    #     self.animator.play_sound()    # 试验素材 试.mp3
    #     self._spawn_item_by_key("microphone")
    #
    # def start_dancing(self):      # 跳舞（B 站/抖音新视频触发）
    #     if not self.sm.transition_to(PetState.DANCING): return
    #     self.animator.play(PetState.DANCING)
    #
    # def start_running(self):      # 小跑（需要和 WALKING 配合行走逻辑，这里先只切状态）
    #     if not self.sm.transition_to(PetState.RUNNING): return
    #     self.animator.play(PetState.RUNNING)
    #
    # def start_crying(self):       # 哭
    #     if not self.sm.transition_to(PetState.CRYING): return
    #     self.animator.play(PetState.CRYING)
    #     QTimer.singleShot(1000, lambda: self._spawn_item_by_key("tissue"))
    #
    # def start_stretching(self):   # 伸懒腰
    #     if not self.sm.transition_to(PetState.STRETCHING): return
    #     self.animator.play(PetState.STRETCHING)
    #     QTimer.singleShot(2500, lambda: (self.sm.transition_to(PetState.IDLE), self.animator.play(PetState.IDLE)))
    #
    # def start_laughing(self):     # 大笑
    #     if not self.sm.transition_to(PetState.LAUGHING): return
    #     self.animator.play(PetState.LAUGHING)
    #     QTimer.singleShot(2500, lambda: (self.sm.transition_to(PetState.HAPPY), self.animator.play(PetState.HAPPY)))
    #
    # def start_zoning_out(self):   # 放空
    #     if not self.sm.transition_to(PetState.ZONING_OUT): return
    #     self.animator.play(PetState.ZONING_OUT)
    #
    # def start_napping(self):      # 打盹（浅睡）
    #     if not self.sm.transition_to(PetState.NAPPING): return
    #     self.animator.play(PetState.NAPPING)
    #
    # def start_eating_snack(self): # 吃零食（冰淇淋）
    #     if not self.sm.transition_to(PetState.EATING_SNACK): return
    #     self.animator.play(PetState.EATING_SNACK)
    #     QTimer.singleShot(2500, lambda: self._spawn_item_by_key("ice_cream"))
    #     QTimer.singleShot(3500, lambda: (self.sm.transition_to(PetState.IDLE), self.animator.play(PetState.IDLE)))
    #
    # def start_reading_phone(self):# 看书 / 玩手机（挂机）
    #     if not self.sm.transition_to(PetState.READING): return
    #     self.animator.play(PetState.READING)
    #     # 试验素材暂代：手机 + 书各掉一张（暂时都用同一张占位）
    #     QTimer.singleShot(500, lambda: self._spawn_item_by_key("phone"))
    #     QTimer.singleShot(1200, lambda: self._spawn_item_by_key("book"))
    # ==========================================================================

    def cleanup(self):
        """清理所有活跃物品"""
        for item in self._active_items:
            item.close()
        self._active_items.clear()
