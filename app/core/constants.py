"""常量与枚举定义."""

from enum import Enum


class TimerState(Enum):
    """计时器状态."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class DisplayMode(Enum):
    """悬浮球显示模式."""
    POMODORO = "pomodoro"
    MONITOR = "monitor"


# 悬浮球默认尺寸（像素）
BALL_SIZE = 120

# 默认设置值
DEFAULT_SETTINGS = {
    "duration_seconds": 1500,
    "theme": "Neon Cyan",
    "opacity": 0.85,
    "window_x": -1,
    "window_y": -1,
    "sound_enabled": True,
    "sound_volume": 0.8,
    "always_on_top": True,
    "hotkey": "Ctrl+Shift+F11",
    "hotkey_enabled": True,
    "auto_start": False,
    "startup_mode": "pomodoro",
    "snap_enabled": True,
    "theme_cycle_enabled": False,
}

# 预设时长选项（分钟）
DURATION_OPTIONS = [10, 15, 20, 25, 30, 45, 50]

# 透明度范围
OPACITY_MIN = 0.1
OPACITY_MAX = 1.0
OPACITY_STEP = 0.05

# 性能监控动画参数
ANIM_FRAME_MS = 33       # 动画帧间隔 ~30fps
ANIM_SMOOTHING = 0.20     # EMA 平滑系数

# 屏幕边缘吸附阈值（像素）
SNAP_THRESHOLD = 30
# 吸附后露出的"尾巴"宽度（像素）
TAIL_WIDTH = 20
# 吸附条自身宽度（像素）
BAR_WIDTH = 10
