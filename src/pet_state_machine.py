"""FSM 有限状态机模块

管理宠物的状态定义和状态转换。
每个状态有对应的行为，状态之间通过触发条件进行转换。
"""

from enum import Enum

from PySide6.QtCore import QObject, Signal


class PetState(Enum):
    """宠物状态枚举"""
    IDLE = "idle"              # 待机
    WALKING = "walking"       # 行走
    DRAGGING = "dragging"     # 被拖拽
    EATING = "eating"         # 吃东西
    ASKING_FOOD = "asking"    # 求投喂
    FEEDING = "feeding"       # 喂食
    RELEASED = "released"     # 松开（拖拽结束过渡）
    SLEEPING = "sleeping"     # 睡觉（预留）
    PLAYING = "playing"       # 玩耍（预留）
    ANGRY = "angry"           # 生气（预留）


# 状态是否可被打断（用于判断是否允许强制切换状态）
INTERRUPTIBLE = {
    PetState.IDLE: True,
    PetState.WALKING: True,
    PetState.DRAGGING: False,
    PetState.EATING: False,
    PetState.ASKING_FOOD: True,
    PetState.FEEDING: False,
    PetState.RELEASED: True,
    PetState.SLEEPING: True,
    PetState.PLAYING: True,
    PetState.ANGRY: True,
}


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
