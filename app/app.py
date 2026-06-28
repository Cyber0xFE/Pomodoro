"""应用程序启动与模块组装."""

import os
import sys
import winreg

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu


def _resource_path(relative_path: str) -> str:
    """获取资源文件路径，兼容 PyInstaller 打包和开发模式."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.abspath(".")
    return os.path.join(base, relative_path)

from app.core.constants import BALL_SIZE, DisplayMode, DURATION_OPTIONS
from app.core.settings import SettingsManager
from app.core.timer import PomodoroTimer
from app.core.monitor import PerformanceMonitor
from app.themes.theme_manager import ThemeManager
from app.ui.context_menu import ContextMenu
from app.ui.floating_ball import FloatingBall
from app.ui.settings_dialog import SettingsDialog
from app.utils.hotkey import register_hotkey, unregister_hotkey, parse_hotkey
from app.utils.brightness import BrightnessController
from app.utils.screen_utils import get_default_position
from app.utils.single_instance import acquire_app_lock


class PomodoroApp:
    """番茄钟应用主控制器."""

    def __init__(self, app_lock):
        self._app_lock = app_lock  # 持有引用防止 GC 回收
        self._settings = SettingsManager()
        self._theme_manager = ThemeManager()
        self._timer = PomodoroTimer()
        self._monitor = PerformanceMonitor()
        self._hotkey_hwnd = None
        self._brightness = BrightnessController()

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
        self._ball.brightness_up_pressed.connect(
            lambda: self._adjust_brightness(+1))
        self._ball.brightness_down_pressed.connect(
            lambda: self._adjust_brightness(-1))

        # 退出时清理亮度控制器持久化进程
        QApplication.instance().aboutToQuit.connect(self._brightness.cleanup)

        # 监听设置变更（开机启动等需要即时生效的项）
        self._settings.setting_changed.connect(self._on_setting_changed)

        # 皮肤轮播定时器
        self._theme_cycle_timer = QTimer(self._ball)
        self._theme_cycle_timer.timeout.connect(self._on_theme_cycle_tick)
        if self._settings.theme_cycle_enabled:
            self._theme_cycle_timer.start(30_000)

        # 初始主题
        saved_theme = self._settings.theme
        self._theme_manager.apply(saved_theme)

        # 初始时长
        saved_duration = self._settings.duration_seconds
        self._timer.set_duration(saved_duration)

        # 位置
        self._restore_position()

        # 系统托盘
        self._setup_tray()

        # 默认启动模式
        if self._settings.startup_mode == "monitor":
            self._ball.set_display_mode(DisplayMode.MONITOR)
            self._tray_mode_action.setText("切换至番茄钟")

    def show(self):
        """显示悬浮球."""
        self._ball.show()
        self._tray.show()
        self._register_hotkeys()

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
            new_duration = self._settings.duration_seconds
            self._timer.set_duration(new_duration)
            self._timer.reset()
            # 热键可能已修改，重新注册
            self._unregister_hotkeys()
            self._register_hotkeys()

    # ── 系统托盘 ──────────────────────────────────────

    def _setup_tray(self):
        """创建系统托盘图标和菜单."""
        icon_path = _resource_path("app/assets/icons/pomodoro.ico")
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
            # 左键单击 — 球隐藏时才显示，已可见则不做任何事
            if not self._ball.isVisible():
                self._ball.show()
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
        """设置番茄钟时长（从预设分钟数）."""
        total_secs = minutes * 60
        self._settings.duration_seconds = total_secs
        self._timer.set_duration(total_secs)
        self._timer.reset()

    def _apply_theme(self, name: str):
        """更换主题."""
        self._theme_manager.apply(name)
        self._settings.theme = name

    def _on_theme_cycle_tick(self):
        """轮播定时器触发 — 切换到下一个皮肤."""
        names = self._theme_manager.theme_names
        if len(names) < 2:
            return
        current = self._settings.theme
        try:
            idx = names.index(current)
        except ValueError:
            idx = 0
        next_idx = (idx + 1) % len(names)
        self._apply_theme(names[next_idx])

    # ── 可见性切换 ────────────────────────────────────

    def _toggle_visibility(self):
        """显示/隐藏悬浮球."""
        if self._ball.isVisible():
            self._ball.hide()
        else:
            self._ball.show()
        self._update_tray_toggle_label()

    # ── 全局热键 ──────────────────────────────────────

    def _unregister_hotkeys(self):
        """注销所有已注册的全局热键."""
        if self._hotkey_hwnd is not None:
            for hid in (1, 2, 3):
                unregister_hotkey(self._hotkey_hwnd, hotkey_id=hid)
            self._hotkey_hwnd = None

    def _register_hotkeys(self):
        """注册所有已配置的全局热键."""
        hwnd = int(self._ball.winId())

        # 热键 ID=1 — 显示/隐藏
        if self._settings.hotkey_enabled:
            hotkey_str = self._settings.hotkey
            parsed = parse_hotkey(hotkey_str)
            if parsed is not None:
                modifiers, vk = parsed
                print(f"[Hotkey] 注册显示/隐藏热键: {hotkey_str!r}, "
                      f"HWND=0x{hwnd:X}, mod=0x{modifiers:X}, vk=0x{vk:X}")
                register_hotkey(hwnd, modifiers, vk, hotkey_id=1)
            else:
                print(f"[Hotkey] 显示/隐藏热键解析失败: {hotkey_str!r}")

        # 热键 ID=2 — 亮度增加
        if self._settings.brightness_hotkey_enabled:
            hotkey_str = self._settings.brightness_up_hotkey
            if hotkey_str:
                parsed = parse_hotkey(hotkey_str)
                if parsed is not None:
                    modifiers, vk = parsed
                    print(f"[Hotkey] 注册亮度增加热键: {hotkey_str!r}")
                    register_hotkey(hwnd, modifiers, vk, hotkey_id=2)
                else:
                    print(f"[Hotkey] 亮度增加热键解析失败: {hotkey_str!r}")

            # 热键 ID=3 — 亮度降低
            hotkey_str = self._settings.brightness_down_hotkey
            if hotkey_str:
                parsed = parse_hotkey(hotkey_str)
                if parsed is not None:
                    modifiers, vk = parsed
                    print(f"[Hotkey] 注册亮度降低热键: {hotkey_str!r}")
                    register_hotkey(hwnd, modifiers, vk, hotkey_id=3)
                else:
                    print(f"[Hotkey] 亮度降低热键解析失败: {hotkey_str!r}")

        self._hotkey_hwnd = hwnd

    # ── 亮度调节 ──────────────────────────────────────

    def _adjust_brightness(self, direction: int):
        """调节屏幕亮度（方向：+1 增加 / -1 降低）。"""
        step = self._settings.brightness_step
        delta = direction * step
        new_value = self._brightness.adjust_brightness(delta)
        if new_value is not None:
            print(f"[Brightness] 亮度调整为 {new_value}% (Δ={delta})")
        else:
            print("[Brightness] 亮度调节失败（显示器可能不支持 WMI 亮度控制）")

    # ── 开机启动 ──────────────────────────────────────

    _AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _AUTOSTART_NAME = "DX3906"

    def _on_setting_changed(self, key: str, value):
        """设置变更回调，处理需即时生效的项."""
        if key == "auto_start":
            self._toggle_autostart(value)
        elif key == "theme_cycle_enabled":
            if value:
                self._theme_cycle_timer.start(30_000)
            else:
                self._theme_cycle_timer.stop()

    def _toggle_autostart(self, enabled: bool):
        """写入或删除开机启动注册表项."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._AUTOSTART_KEY, 0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)
        except OSError:
            return

        if enabled:
            exe_path = sys.executable
            winreg.SetValueEx(key, self._AUTOSTART_NAME, 0,
                              winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, self._AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        key.Close()


def main():
    """应用入口."""
    # 高 DPI 适配
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("DX3906")
    app.setApplicationDisplayName("番茄钟悬浮球")
    app.setQuitOnLastWindowClosed(False)

    # 单实例检测
    app_lock = acquire_app_lock()
    if app_lock is None:
        print("番茄钟已在运行中")
        sys.exit(0)

    # 启动
    pomodoro = PomodoroApp(app_lock)
    pomodoro.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
