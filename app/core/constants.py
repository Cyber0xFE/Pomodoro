"""常量与枚举定义."""

from enum import Enum


class TimerState(Enum):
    """计时器状态."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


# 悬浮球默认尺寸（像素）
BALL_SIZE = 120

# 默认设置值
DEFAULT_SETTINGS = {
    "duration_minutes": 25,
    "theme": "Neon Cyan",
    "opacity": 0.85,
    "window_x": -1,
    "window_y": -1,
    "sound_enabled": True,
    "sound_volume": 0.8,
    "always_on_top": True,
}

# 预设时长选项（分钟）
DURATION_OPTIONS = [10, 15, 20, 25, 30, 45, 50]

# 透明度范围
OPACITY_MIN = 0.1
OPACITY_MAX = 1.0
OPACITY_STEP = 0.05
