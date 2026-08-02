"""FSM（有限状态机）模块.

按照框架文档第 3 章的状态机设计实现。
状态定义、转换条件、动画映射均与框架文档保持一致。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class PetState(Enum):
    """宠物状态枚举.

    对应框架文档 3.1 节状态定义表。
    """

    IDLE = auto()          # 待机：宠物静止站立，无动作
    WALKING = auto()       # 行走：宠物在桌面上随机走动
    DRAGGING = auto()      # 被拖拽：用户按住左键拖动宠物
    EATING = auto()        # 吃东西：播放吃猪蹄动画
    ASKING_FOOD = auto()   # 求投喂：宠物做出期待表情，刷出葡萄汁图片
    FEEDING = auto()       # 喂食：用户投喂后宠物吃东西，然后吐出豆腐
    RELEASED = auto()      # 松开：拖拽结束后播放的过渡动画
    SLEEPING = auto()      # 睡觉（待扩展）
    PLAYING = auto()       # 玩耍（待扩展）
    ANGRY = auto()         # 生气（待扩展）


# 状态是否可被打断（对应框架文档 3.1 节"是否可被打断"列）
INTERRUPTIBLE_STATES: frozenset[PetState] = frozenset({
    PetState.IDLE,
    PetState.WALKING,
    PetState.ASKING_FOOD,
    PetState.RELEASED,
    PetState.SLEEPING,
    PetState.PLAYING,
    PetState.ANGRY,
})


# 状态对应的动画配置（对应框架文档 3.3 节动画帧映射表）
# (帧数量, 帧率 FPS)
STATE_ANIMATION_CONFIG: dict[PetState, tuple[int, int]] = {
    PetState.IDLE:        (8, 10),
    PetState.WALKING:     (12, 15),
    PetState.DRAGGING:    (1, 1),    # 静态图片
    PetState.RELEASED:    (5, 15),
    PetState.EATING:      (20, 20),
    PetState.ASKING_FOOD: (10, 12),
    PetState.FEEDING:     (25, 20),
    PetState.SLEEPING:    (6, 5),
    PetState.PLAYING:     (15, 15),
    PetState.ANGRY:       (10, 12),
}


# 状态对应的动画帧目录名（assets/ 下的子目录名）
STATE_ASSETS_DIR: dict[PetState, str] = {
    PetState.IDLE:        "idle",
    PetState.WALKING:     "walking",
    PetState.DRAGGING:    "dragging",
    PetState.RELEASED:    "released",
    PetState.EATING:      "eating",
    PetState.ASKING_FOOD: "asking_food",
    PetState.FEEDING:     "feeding",
    PetState.SLEEPING:    "sleeping",
    PetState.PLAYING:     "playing",
    PetState.ANGRY:       "angry",
}


# 触发条件类型（对应框架文档 3.2 节状态转换条件表）
class Trigger(Enum):
    """状态转换触发条件."""

    RANDOM_WALK = auto()          # 随机触发行走
    REACHED_BOUNDARY = auto()     # 到达屏幕边界
    RANDOM_STOP = auto()          # 随机停止
    LEFT_PRESS = auto()           # 用户左键按住宠物（移动距离>5像素）
    LEFT_RELEASE = auto()         # 用户松开左键
    MENU_EAT = auto()             # 右键选择"吃东西"
    MENU_ASK_FOOD = auto()        # 右键选择"求投喂"
    MENU_FEED = auto()            # 右键选择"喂食"
    FOOD_CLICKED = auto()         # 用户点击葡萄汁图片
    ASK_FOOD_TIMEOUT = auto()     # 超时未投喂
    ANIMATION_DONE = auto()       # 动画播放完毕
    LONG_IDLE = auto()            # 长时间未互动
    USER_CLICK = auto()           # 用户点击宠物
    SLEEP_DONE = auto()           # 睡眠时间结束
    PLAY_DONE = auto()            # 玩耍时间结束
    USER_SOOTHE = auto()          # 用户安抚


# 默认状态转换表（对应框架文档 3.2 节）
# 键: (当前状态, 触发条件), 值: 目标状态
_DEFAULT_TRANSITIONS: dict[tuple[PetState, Trigger], PetState] = {
    (PetState.IDLE,        Trigger.RANDOM_WALK):      PetState.WALKING,
    (PetState.IDLE,        Trigger.MENU_EAT):         PetState.EATING,
    (PetState.IDLE,        Trigger.MENU_ASK_FOOD):    PetState.ASKING_FOOD,
    (PetState.IDLE,        Trigger.LEFT_PRESS):       PetState.DRAGGING,
    (PetState.IDLE,        Trigger.LONG_IDLE):        PetState.SLEEPING,
    (PetState.WALKING,     Trigger.REACHED_BOUNDARY): PetState.IDLE,
    (PetState.WALKING,     Trigger.LEFT_PRESS):       PetState.DRAGGING,
    (PetState.WALKING,     Trigger.RANDOM_STOP):      PetState.IDLE,
    (PetState.DRAGGING,    Trigger.LEFT_RELEASE):     PetState.RELEASED,
    (PetState.RELEASED,    Trigger.ANIMATION_DONE):   PetState.IDLE,
    (PetState.EATING,      Trigger.ANIMATION_DONE):   PetState.IDLE,
    (PetState.ASKING_FOOD, Trigger.FOOD_CLICKED):     PetState.FEEDING,
    (PetState.ASKING_FOOD, Trigger.ASK_FOOD_TIMEOUT): PetState.IDLE,
    (PetState.FEEDING,     Trigger.ANIMATION_DONE):   PetState.IDLE,
    (PetState.SLEEPING,    Trigger.USER_CLICK):       PetState.IDLE,
    (PetState.SLEEPING,    Trigger.SLEEP_DONE):       PetState.IDLE,
    (PetState.PLAYING,     Trigger.PLAY_DONE):        PetState.IDLE,
    (PetState.ANGRY,       Trigger.USER_SOOTHE):      PetState.IDLE,
}


@dataclass
class StateChangedPayload:
    """状态切换时回调的载荷."""

    old_state: PetState
    new_state: PetState
    trigger: Trigger


class PetStateMachine:
    """宠物有限状态机.

    使用方式：
        fsm = PetStateMachine()
        fsm.on_state_changed.append(my_callback)
        fsm.transition(Trigger.LEFT_PRESS)
        print(fsm.current_state)
    """

    def __init__(self, initial_state: PetState = PetState.IDLE) -> None:
        self._current = initial_state
        self._transitions: dict[tuple[PetState, Trigger], PetState] = dict(
            _DEFAULT_TRANSITIONS
        )
        # 状态切换回调列表
        self.on_state_changed: list[Callable[[StateChangedPayload], None]] = []

    @property
    def current_state(self) -> PetState:
        """当前状态."""
        return self._current

    def can_transition(self, trigger: Trigger) -> bool:
        """判断当前状态下能否响应指定触发条件."""
        return (self._current, trigger) in self._transitions

    def transition(self, trigger: Trigger) -> PetState:
        """尝试根据触发条件切换状态.

        Args:
            trigger: 触发条件。

        Returns:
            切换后的状态（若未切换则为原状态）。

        Raises:
            ValueError: 当前状态无法响应该触发条件。
        """
        key = (self._current, trigger)
        if key not in self._transitions:
            raise ValueError(
                f"状态 {self._current.name} 无法响应触发条件 {trigger.name}"
            )

        old_state = self._current
        new_state = self._transitions[key]
        self._current = new_state

        payload = StateChangedPayload(
            old_state=old_state, new_state=new_state, trigger=trigger
        )
        for callback in self.on_state_changed:
            callback(payload)

        return new_state

    def try_transition(self, trigger: Trigger) -> bool:
        """尝试切换状态，失败时返回 False 而非抛出异常."""
        try:
            self.transition(trigger)
            return True
        except ValueError:
            return False

    def is_interruptible(self) -> bool:
        """当前状态是否可被打断."""
        return self._current in INTERRUPTIBLE_STATES

    def add_transition(
        self, from_state: PetState, trigger: Trigger, to_state: PetState
    ) -> None:
        """添加自定义状态转换规则（用于扩展）."""
        self._transitions[(from_state, trigger)] = to_state


__all__ = [
    "PetState",
    "Trigger",
    "INTERRUPTIBLE_STATES",
    "STATE_ANIMATION_CONFIG",
    "STATE_ASSETS_DIR",
    "StateChangedPayload",
    "PetStateMachine",
]
