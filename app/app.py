"""应用程序启动与模块组装."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from app.core.constants import BALL_SIZE, DisplayMode, DURATION_OPTIONS
from app.core.settings import SettingsManager
from app.core.timer import PomodoroTimer
from app.core.monitor import PerformanceMonitor
from app.themes.theme_manager import ThemeManager
from app.ui.context_menu import ContextMenu
from app.ui.floating_ball import FloatingBall
from app.ui.settings_dialog import SettingsDialog
from app.utils.hotkey import register_hotkey, unregister_hotkey, parse_hotkey
from app.utils.screen_utils import get_default_position
from app.utils.single_instance import is_already_running


class PomodoroApp:
    """番茄钟应用主控制器."""

    def __init__(self):
        self._settings = SettingsManager()
        self._theme_manager = ThemeManager()
        self._timer = PomodoroTimer()
        self._monitor = PerformanceMonitor()
        self._hotkey_hwnd = None

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

        # 连接热键信号
        self._ball.hotkey_pressed.connect(self._toggle_visibility)

        # 初始主题
        saved_theme = self._settings.theme
        self._theme_manager.apply(saved_theme)

        # 初始时长
        saved_duration = self._settings.duration_minutes
        self._timer.set_duration(saved_duration)

        # 位置
        self._restore_position()

        # 系统托盘
        self._setup_tray()

    def show(self):
        """显示悬浮球."""
        self._ball.show()
        self._tray.show()
        self._register_hotkey()

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
            # 热键可能已修改，重新注册
            self._unregister_hotkey()
            self._register_hotkey()

    # ── 系统托盘 ──────────────────────────────────────

    def _setup_tray(self):
        """创建系统托盘图标和菜单."""
        icon_path = "app/assets/icons/pomodoro.ico"
        self._tray = QSystemTrayIcon(QIcon(icon_path), self._ball)
        self._tray.setToolTip("番茄钟悬浮球")

        # 构建托盘菜单
        self._tray_menu = QMenu()

        self._tray_toggle_action = QAction("隐藏悬浮球", self._tray_menu)
        self._tray_toggle_action.triggered.connect(self._toggle_visibility)
        self._tray_menu.addAction(self._tray_toggle_action)

        self._tray_menu.addSeparator()

        # 模式切换
        self._tray_mode_action = QAction("切换至性能监控", self._tray_menu)
        self._tray_mode_action.triggered.connect(self._on_tray_switch_mode)
        self._tray_menu.addAction(self._tray_mode_action)

        self._tray_menu.addSeparator()

        # 设置时长子菜单
        duration_menu = self._tray_menu.addMenu("设置时长")
        for mins in DURATION_OPTIONS:
            action = QAction(f"{mins} 分钟", duration_menu)
            action.triggered.connect(lambda checked, m=mins: self._set_duration(m))
            duration_menu.addAction(action)

        # 更换皮肤子菜单
        theme_menu = self._tray_menu.addMenu("更换皮肤")
        for name in self._theme_manager.theme_names:
            action = QAction(name, theme_menu)
            action.triggered.connect(lambda checked, n=name: self._apply_theme(n))
            theme_menu.addAction(action)

        self._tray_menu.addSeparator()

        # 设置
        settings_action = QAction("设置", self._tray_menu)
        settings_action.triggered.connect(self._open_settings)
        self._tray_menu.addAction(settings_action)

        self._tray_menu.addSeparator()

        # 退出
        quit_action = QAction("退出", self._tray_menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        self._tray_menu.addAction(quit_action)

        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """托盘图标点击事件."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # 左键单击 — 切换可见性
            self._toggle_visibility()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            # 右键 — 已由 contextMenu 处理，这里更新菜单状态
            self._update_tray_toggle_label()

    def _on_tray_switch_mode(self):
        """托盘菜单 — 切换显示模式."""
        if self._ball.display_mode == DisplayMode.POMODORO:
            self._switch_display_mode(DisplayMode.MONITOR)
            self._tray_mode_action.setText("切换至番茄钟")
        else:
            self._switch_display_mode(DisplayMode.POMODORO)
            self._tray_mode_action.setText("切换至性能监控")

    def _update_tray_toggle_label(self):
        """根据悬浮球可见性更新托盘菜单文字."""
        if self._ball.isVisible():
            self._tray_toggle_action.setText("隐藏悬浮球")
        else:
            self._tray_toggle_action.setText("显示悬浮球")

    def _set_duration(self, minutes: int):
        """设置番茄钟时长."""
        self._settings.duration_minutes = minutes
        self._timer.set_duration(minutes)
        self._timer.reset()

    def _apply_theme(self, name: str):
        """更换主题."""
        self._theme_manager.apply(name)
        self._settings.theme = name

    # ── 可见性切换 ────────────────────────────────────

    def _toggle_visibility(self):
        """显示/隐藏悬浮球."""
        if self._ball.isVisible():
            self._ball.hide()
        else:
            self._ball.show()
        self._update_tray_toggle_label()

    # ── 全局热键 ──────────────────────────────────────

    def _unregister_hotkey(self):
        """注销当前全局热键."""
        if self._hotkey_hwnd is not None:
            unregister_hotkey(self._hotkey_hwnd)
            self._hotkey_hwnd = None

    def _register_hotkey(self):
        """注册全局热键."""
        if not self._settings.hotkey_enabled:
            print("[Hotkey] hotkey_enabled=false, 跳过注册")
            return
        hotkey_str = self._settings.hotkey
        parsed = parse_hotkey(hotkey_str)
        if parsed is None:
            print(f"[Hotkey] 解析热键字符串失败: {hotkey_str!r}")
            return
        modifiers, vk = parsed
        hwnd = int(self._ball.winId())
        print(f"[Hotkey] 尝试注册热键: {hotkey_str!r}, "
              f"HWND=0x{hwnd:X}, mod=0x{modifiers:X}, vk=0x{vk:X}")
        if register_hotkey(hwnd, modifiers, vk):
            self._hotkey_hwnd = hwnd


def main():
    """应用入口."""
    # 高 DPI 适配
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("PomodoroBall")
    app.setApplicationDisplayName("番茄钟悬浮球")
    app.setQuitOnLastWindowClosed(False)

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
