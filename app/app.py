"""应用程序启动与模块组装."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.constants import BALL_SIZE, DisplayMode
from app.core.settings import SettingsManager
from app.core.timer import PomodoroTimer
from app.core.monitor import PerformanceMonitor
from app.themes.theme_manager import ThemeManager
from app.ui.context_menu import ContextMenu
from app.ui.floating_ball import FloatingBall
from app.ui.settings_dialog import SettingsDialog
from app.utils.screen_utils import get_default_position
from app.utils.single_instance import is_already_running


class PomodoroApp:
    """番茄钟应用主控制器."""

    def __init__(self):
        self._settings = SettingsManager()
        self._theme_manager = ThemeManager()
        self._timer = PomodoroTimer()
        self._monitor = PerformanceMonitor()

        # 创建悬浮球
        self._ball = FloatingBall(
            timer=self._timer,
            settings=self._settings,
            theme_manager=self._theme_manager,
            monitor=self._monitor,
        )

        # 创建右键菜单
        self._context_menu = ContextMenu(
            timer=self._timer,
            settings=self._settings,
            theme_manager=self._theme_manager,
            on_adjust_opacity=self._open_settings,
            on_switch_mode=self._switch_display_mode,
        )

        # 连接右键信号
        self._ball.right_clicked.connect(self._show_context_menu)

        # 初始主题
        saved_theme = self._settings.theme
        self._theme_manager.apply(saved_theme)

        # 初始时长
        saved_duration = self._settings.duration_minutes
        self._timer.set_duration(saved_duration)

        # 位置
        self._restore_position()

    def show(self):
        """显示悬浮球."""
        self._ball.show()

    def _restore_position(self):
        """恢复上次窗口位置，或使用默认位置."""
        x = self._settings.window_x
        y = self._settings.window_y
        if x < 0 or y < 0:
            x, y = get_default_position(BALL_SIZE)
        self._ball.move(x, y)

    def _show_context_menu(self):
        """在鼠标位置弹出右键菜单."""
        self._context_menu.set_display_mode(self._ball.display_mode)
        self._context_menu.exec(self._ball.cursor().pos())

    def _switch_display_mode(self, mode: DisplayMode):
        """切换悬浮球显示模式."""
        self._ball.set_display_mode(mode)

    def _open_settings(self):
        """打开设置对话框."""
        dialog = SettingsDialog(self._settings, self._ball)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            # 设置已保存，同步到计时器
            new_duration = self._settings.duration_minutes
            self._timer.set_duration(new_duration)
            self._timer.reset()


def main():
    """应用入口."""
    # 高 DPI 适配
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PomodoroBall")
    app.setApplicationDisplayName("番茄钟悬浮球")

    # 单实例检测
    if is_already_running():
        print("番茄钟已在运行中")
        sys.exit(0)

    # 启动
    pomodoro = PomodoroApp()
    pomodoro.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
