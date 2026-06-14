"""屏幕几何辅助工具."""

from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QApplication


def get_available_geometry() -> "QRect":
    """获取主屏幕可用区域（排除任务栏）."""
    return QApplication.primaryScreen().availableGeometry()


def get_default_position(ball_size: int) -> tuple[int, int]:
    """计算默认位置：屏幕右下角，距边缘 40px."""
    geo = get_available_geometry()
    x = geo.right() - ball_size - 40
    y = geo.bottom() - ball_size - 40
    return x, y
