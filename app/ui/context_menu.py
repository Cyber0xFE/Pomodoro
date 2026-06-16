"""右键上下文菜单."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu

from app.core.constants import DURATION_OPTIONS, DisplayMode
from app.core.timer import PomodoroTimer
from app.core.settings import SettingsManager
from app.themes.theme_manager import ThemeManager


class ContextMenu(QMenu):
    """悬浮球右键菜单 — 根据显示模式动态构建."""

    def __init__(
        self,
        timer: PomodoroTimer,
        settings: SettingsManager,
        theme_manager: ThemeManager,
        on_adjust_opacity=None,
        on_switch_mode=None,
        parent=None,
    ):
        super().__init__(parent)
        self._timer = timer
        self._settings = settings
        self._theme_manager = theme_manager
        self._on_adjust_opacity = on_adjust_opacity
        self._on_switch_mode = on_switch_mode
        self._current_mode = DisplayMode.POMODORO

        self._build_menu()
        self._apply_style()

    def set_display_mode(self, mode: DisplayMode):
        """同步当前显示模式，在 exec() 前调用."""
        if mode != self._current_mode:
            self._current_mode = mode
            self.clear()
            self._build_menu()

    def _build_menu(self):
        """构建菜单项，根据当前显示模式调整."""
        if self._current_mode == DisplayMode.POMODORO:
            # ── 设置时长 ──
            duration_menu = self.addMenu("⏱ 设置时长")
            for mins in DURATION_OPTIONS:
                action = duration_menu.addAction(f"{mins} 分钟")
                action.triggered.connect(self._make_duration_handler(mins))

            self.addSeparator()

            # ── 重置 ──
            reset_action = self.addAction("🔄 重置计时器")
            reset_action.triggered.connect(self._timer.reset)

            self.addSeparator()

        # ── 模式切换 ──
        if self._current_mode == DisplayMode.POMODORO:
            mode_action = self.addAction("📊 切换到性能监控")
            target_mode = DisplayMode.MONITOR
        else:
            mode_action = self.addAction("⏱ 切换到番茄钟")
            target_mode = DisplayMode.POMODORO

        if self._on_switch_mode:
            mode_action.triggered.connect(
                self._make_mode_switch_handler(target_mode)
            )

        self.addSeparator()

        # ── 更换皮肤 ──
        theme_menu = self.addMenu("🎨 更换皮肤")
        for name in self._theme_manager.theme_names:
            action = theme_menu.addAction(name)
            action.triggered.connect(self._make_theme_handler(name))

        self.addSeparator()

        # ── 设置 ──
        settings_action = self.addAction("🔧 设置")
        settings_action.triggered.connect(self._on_open_settings)

        # ── 退出 ──
        quit_action = self.addAction("❌ 退出")
        quit_action.triggered.connect(QApplication.instance().quit)

    def _make_duration_handler(self, mins: int):
        """创建时长设置的回调."""
        def handler():
            total_secs = mins * 60
            self._settings.duration_seconds = total_secs
            self._timer.set_duration(total_secs)
        return handler

    def _make_theme_handler(self, name: str):
        """创建主题切换的回调."""
        def handler():
            self._theme_manager.apply(name)
            self._settings.theme = name
        return handler

    def _make_mode_switch_handler(self, target_mode: DisplayMode):
        """创建模式切换的回调."""
        def handler():
            if self._on_switch_mode:
                self._on_switch_mode(target_mode)
        return handler

    def _on_open_settings(self):
        if self._on_adjust_opacity:
            self._on_adjust_opacity()

    def _apply_style(self):
        """应用菜单样式."""
        self.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 4px 0;
                font-size: 14px;
            }
            QMenu::item {
                padding: 8px 32px 8px 20px;
            }
            QMenu::item:selected {
                background-color: #3a3a3a;
                border-radius: 3px;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 4px 12px;
            }
        """)
