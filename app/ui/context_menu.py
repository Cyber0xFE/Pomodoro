"""右键上下文菜单."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu

from app.core.constants import DURATION_OPTIONS
from app.core.timer import PomodoroTimer
from app.core.settings import SettingsManager
from app.themes.theme_manager import ThemeManager


class ContextMenu(QMenu):
    """悬浮球右键菜单."""

    def __init__(
        self,
        timer: PomodoroTimer,
        settings: SettingsManager,
        theme_manager: ThemeManager,
        on_adjust_opacity=None,
        parent=None,
    ):
        super().__init__(parent)
        self._timer = timer
        self._settings = settings
        self._theme_manager = theme_manager
        self._on_adjust_opacity = on_adjust_opacity

        self._build_menu()
        self._apply_style()

    def _build_menu(self):
        """构建菜单项."""
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
            self._settings.duration_minutes = mins
            self._timer.set_duration(mins)
        return handler

    def _make_theme_handler(self, name: str):
        """创建主题切换的回调."""
        def handler():
            self._theme_manager.apply(name)
            self._settings.theme = name
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
