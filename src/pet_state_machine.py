"""FSM 有限状态机模块

管理宠物的状态定义和状态转换。
每个状态有对应的行为，状态之间通过触发条件进行转换。
"""

from enum import Enum

from PySide6.QtCore import QObject, Signal


class PetState(Enum):
    """宠物状态枚举"""
    IDLE = "idle"              # 待机
    WALKING = "walking"        # 行走（旧，保留兼容，实际用 LEFT/RIGHT）
    WALKING_LEFT = "walking_left"   # 往左走
    WALKING_RIGHT = "walking_right" # 往右走
    DRAGGING = "dragging"     # 被拖拽（第一段，一次性）
    DRAGGING_2 = "dragging_2"  # 被拖拽（第二段，循环）
    EATING = "eating"         # 吃东西（第一段）
    EATING_2 = "eating_2"     # 吃东西（第二段）
    ASKING = "asking"         # 撒娇（idle随机触发）
    ASKING_FOOD = "asking_food"  # 求投喂
    FEEDING = "feeding"       # 喂食
    RELEASED = "released"     # 松开（拖拽结束过渡）
    SLEEPING = "sleeping"     # 睡觉（预留）
    PLAYING = "playing"       # 玩耍（预留）
    ANGRY = "angry"           # 生气（预留）
    KISS = "kiss"              # 亲亲（idle随机）
    KIDDING = "kidding"        # 玩闹（idle随机）
    SHOWING = "showing"       # 展示（idle随机）

    # ===========================================================================
    # 以下为「框架文档 v3 §3.1 提到的可扩展动作 + 常见情绪/交互状态」占位枚举。
    # —— 新的代码块，当前 **整体注释掉（COMMENTED OUT）**，暂不生效 ——
    # 素材到位后，做 3 件事就能启用：
    #   1. 把下面 '''...''' 三引号打开 / 或把每行前的 # 去掉；
    #   2. 在 src/pet_animator.py ASSET_MAP 里写对应映射（已在 animator 里同步写好占位）；
    #   3. 在 src/main_window.py 菜单里对应 QAction 解注释 + 连到 InteractionManager。
    # 【素材暂代方案】：在 animator 的扩展 ASSET_MAP 块里，全部先用
    #   ``试.gif``（动画） / ``试.png``（静态图） 作为试验占位素材。
    # ---------------------------------------------------------------------------
    # 扩展状态（框架 v3 §3.1 "可添加：洗澡、生病、开心 等" + 情绪系统 §2.2）
    #
    # HAPPY       = "happy"         # 开心（情绪系统：高情绪值触发）
    # SAD         = "sad"           # 委屈 / 难过
    # SICK        = "sick"          # 生病（咳嗽、无精打采）
    # BATHING     = "bathing"       # 洗澡（泡泡 / 搓澡动作）
    # PATTED      = "patted"        # 被摸头（左键点击宠物，交互反馈 §2.2）
    # POKED       = "poked"         # 被戳一下（左键点击其它部位/连点）
    # SHY         = "shy"           # 害羞（被夸 / 被送东西）
    # SURPRISED   = "surprised"     # 惊讶（弹窗 / 新东西出现）
    # YAWN        = "yawn"          # 打哈欠（IDLE 太久、从 SLEEPING 起来）
    # DRINKING    = "drinking"      # 喝水（饮料投喂，§2.2 可扩展更多投喂物品）
    # SINGING     = "singing"       # 唱歌（语音反馈彩蛋）
    # DANCING     = "dancing"       # 跳舞（B 站/抖音 新视频发布触发）
    # RUNNING     = "running"       # 小跑（情绪值高时替代 WALKING）
    # CRYING      = "crying"        # 哭泣 / 掉眼泪（情绪值太低）
    # STRETCHING  = "stretching"    # 伸懒腰（SLEEPING → IDLE 过渡）
    # LAUGHING    = "laughing"      # 大笑（摸头被挠到痒点 / 笑话彩蛋）
    # ZONING_OUT  = "zoning_out"    # 放空 / 发呆（IDLE 持续太久）
    # NAPPING     = "napping"       # 打盹（浅睡，跟 SLEEPING 深浅两档）
    # EATING_SNACK= "eating_snack"  # 吃零食（冰淇淋/奶茶，§2.2 更多食物类型）
    # READING     = "reading"       # 看书 / 玩手机（挂机状态）
    # ===========================================================================


# 状态是否可被打断（用于判断是否允许强制切换状态）
INTERRUPTIBLE = {
    PetState.IDLE: True,
    PetState.WALKING: True,
    PetState.WALKING_LEFT: True,
    PetState.WALKING_RIGHT: True,
    PetState.DRAGGING: False,
    PetState.DRAGGING_2: False,
    PetState.EATING: False,
    PetState.EATING_2: False,
    PetState.ASKING: True,
    PetState.ASKING_FOOD: True,
    PetState.FEEDING: False,
    PetState.RELEASED: True,
    PetState.SLEEPING: True,
    PetState.PLAYING: True,
    PetState.ANGRY: True,
    PetState.KISS: True,
    PetState.KIDDING: True,
    PetState.SHOWING: True,
}

# 状态动画是否只播放一次（True = 播完发 animation_finished 信号，由 InteractionManager 决定下一步）
# 未列出的状态默认 False（循环播放）
ONE_SHOT = {
    PetState.DRAGGING: True,    # dragging1 → 完后检查是否仍在拖拽
    PetState.EATING: True,      # eating1 → 完后给猪蹄
    PetState.EATING_2: True,    # eating2 → 完后回idle
    PetState.FEEDING: True,     # feeding → 完后给豆腐
    PetState.KISS: True,        # → 回idle
    PetState.KIDDING: True,     # → 回idle
    PetState.SHOWING: True,     # → 回idle
    PetState.ASKING: True,      # → 回idle（idle随机触发）
}

# =============================================================================
# 扩展状态对应的 INTERRUPTIBLE 表（COMMENTED OUT，与上面的扩展枚举配套）
# —— 全部暂代素材，打开上面扩展枚举后再去掉这里的注释即可 ——
#
# EXT_INTERRUPTIBLE = {
#     # PetState.HAPPY:        True,   # 开心可被打断
#     # PetState.SAD:          True,
#     # PetState.SICK:         True,
#     # PetState.BATHING:      False,  # 洗澡过程别打断（跟 EATING 同优先级）
#     # PetState.PATTED:       True,   # 被摸头动作短，可随时打断
#     # PetState.POKED:        True,
#     # PetState.SHY:          True,
#     # PetState.SURPRISED:    True,
#     # PetState.YAWN:         True,   # 打哈欠随时可切
#     # PetState.DRINKING:     False,  # 喝水动作完成后再走
#     # PetState.SINGING:      True,
#     # PetState.DANCING:      True,
#     # PetState.RUNNING:      True,
#     # PetState.CRYING:       True,
#     # PetState.STRETCHING:   True,
#     # PetState.LAUGHING:     True,
#     # PetState.ZONING_OUT:   True,
#     # PetState.NAPPING:      True,   # 打盹可叫醒
#     # PetState.EATING_SNACK: False,  # 吃零食也属于"吃东西"，别中途打断
#     # PetState.READING:      True,
# }
# # 合并回 INTERRUPTIBLE（启用扩展状态后取消下面注释即可一次性并进去）
# # INTERRUPTIBLE.update(EXT_INTERRUPTIBLE)
# =============================================================================



class StateMachine(QObject):
    """有限状态机

    管理状态转换，当状态变化时发出信号。
    """

    # 状态变化信号：参数为 (旧状态, 新状态)
    state_changed = Signal(PetState, PetState)

    def __init__(self, initial_state=PetState.IDLE):
        super().__init__()
        self._state = initial_state
        self._previous_state = initial_state

    @property
    def state(self):
        """当前状态"""
        return self._state

    @property
    def previous_state(self):
        """上一个状态"""
        return self._previous_state

    def can_interrupt(self):
        """当前状态是否可被打断"""
        return INTERRUPTIBLE.get(self._state, True)

    def transition_to(self, new_state):
        """转换到新状态

        如果当前状态不可打断且新状态不是强制优先级，则拒绝转换。
        DRAGGING 状态始终可以强制转换（用户操作优先）。
        """
        if new_state == self._state:
            return True

        # 当前状态不可打断时，只有强制操作（如拖拽）才能切换
        if not self.can_interrupt() and new_state != PetState.DRAGGING:
            return False

        self._previous_state = self._state
        self._state = new_state
        self.state_changed.emit(self._previous_state, self._state)
        return True

    def force_transition(self, new_state):
        """强制转换状态（忽略打断限制）"""
        if new_state == self._state:
            return
        self._previous_state = self._state
        self._state = new_state
        self.state_changed.emit(self._previous_state, self._state)
