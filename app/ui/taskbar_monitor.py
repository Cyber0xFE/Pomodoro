"""任务栏内嵌性能监控窗口.

实现方式（参考 TrafficMonitor 的 Win11 任务栏窗口）:
1. 找到任务栏窗口 ``Shell_TrayWnd``，把本窗口通过 ``SetParent`` 嵌入任务栏；
2. 窗口使用 ``WS_EX_LAYERED`` + ``UpdateLayeredWindow`` 提交像素，
   否则普通子窗口会被 Win11 任务栏的 XAML 合成层遮挡；
3. 用 QImage 绘制内容后拷贝到 DIBSection，再交给 UpdateLayeredWindow 显示；
4. 窗口定位在任务栏图标左侧的空白区，定时跟随任务栏布局变化.
"""

import ctypes
import math
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter,
    QPen)
from PySide6.QtWidgets import QApplication, QMenu

from app.core.constants import ANIM_FRAME_MS
from app.core.constants import TASKBAR_STYLE_OPTIONS
from app.core.monitor import MonitorSnapshot, PerformanceMonitor
from app.core.settings import SettingsManager
from app.themes.theme_manager import Theme, ThemeManager

# ── Win32 常量 ─────────────────────────────────────────
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GWL_STYLE = -16
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SW_HIDE = 0
SW_SHOWNA = 8
ULW_ALPHA = 2
AC_SRC_ALPHA = 1
WM_DESTROY = 0x0002
WM_MOUSEACTIVATE = 0x0021
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
MA_NOACTIVATE = 3


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint,
    ctypes.c_size_t, ctypes.c_ssize_t)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.DefWindowProcW.argtypes = [
    wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.GetWindowRect.restype = wintypes.BOOL
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.SetParent.restype = wintypes.HWND
_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_user32.RegisterClassW.restype = wintypes.ATOM
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.GetDC.restype = wintypes.HDC
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.ScreenToClient.restype = wintypes.BOOL
_user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.UpdateLayeredWindow.restype = wintypes.BOOL
_user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
    wintypes.DWORD, ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_user32.IsWindow.restype = wintypes.BOOL
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.GetDpiForWindow.restype = ctypes.c_uint
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.DestroyWindow.restype = wintypes.BOOL
_user32.DestroyWindow.argtypes = [wintypes.HWND]

_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateDIBSection.restype = wintypes.HBITMAP
_gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(_BITMAPINFOHEADER), ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = wintypes.BOOL
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.restype = wintypes.BOOL
_gdi32.DeleteDC.argtypes = [wintypes.HDC]

_kernel32.GetModuleHandleW.restype = wintypes.HMODULE
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

_WINDOW_CLASS = "Dx3906TaskbarMonitor"

# ── 布局常量（逻辑像素，运行时按 DPI 缩放）───────────────
_FONT_PX = 14
_PAD_X = 8
_MARGIN_Y = 2
_GAP_ARROW = 4
_GAP_LABEL = 6
_PILL_PAD = 4
_PILL_GAP_Y = 2
_PILL_GAP = 6
_CORNER = 5

# 数值平滑时间常数（秒）；网速响应更快
_TAU_PERCENT = 0.22
_TAU_SPEED = 0.12


def _format_speed(bps: float) -> str:
    """紧凑网速文本，如 146B/s、1.2MB/s."""
    if bps >= 1_000_000_000:
        return f"{bps / 1_000_000_000:.1f}GB/s"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f}MB/s"
    if bps >= 1_000:
        return f"{bps / 1_000:.0f}KB/s"
    return f"{bps:.0f}B/s"


class TaskbarMonitor(QObject):
    """内嵌任务栏的性能监控窗口（CPU / 内存 / 上下行网速）."""

    def __init__(
        self,
        monitor: PerformanceMonitor,
        settings: SettingsManager,
        theme_manager: ThemeManager,
        on_open_settings=None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._monitor = monitor
        self._settings = settings
        self._theme_manager = theme_manager
        self._on_open_settings = on_open_settings

        self._hwnd: int | None = None
        self._taskbar: int | None = None
        self._visible = False

        self._memdc = None
        self._bitmap = None
        self._bits = None
        self._screen_dc = None
        self._image: QImage | None = None
        self._w = 0
        self._h = 0
        self._layout_key: tuple | None = None

        # 最近一次监控数据（目标值）
        self._cpu = 0.0
        self._mem = 0.0
        self._up = 0.0
        self._down = 0.0

        # 动画插值后的显示值
        self._anim_cpu = 0.0
        self._anim_mem = 0.0
        self._anim_up = 0.0
        self._anim_down = 0.0
        # 网速动态上限（快速上升、缓慢回落）
        self._up_ceiling = 1024.0
        self._down_ceiling = 1024.0

        self._phase = 0.0        # 呼吸/流光相位
        self._flow_phase = 0.0   # 箭头浮动相位
        self._last_ts = 0.0

        # 任务栏尺寸/位置缓存
        self._dpi = 96
        self._dst: tuple[int, int] | None = None
        self._placed: tuple | None = None

        # 任务栏几何缓存（用于检测布局变化）
        self._geo_key: tuple | None = None

        self._theme: Theme | None = theme_manager.current
        self._style = self._normalise_style(settings.taskbar_monitor_style)
        self._alert_threshold = self._normalise_threshold(
            settings.monitor_alert_threshold)

        # 窗口过程回调必须保持引用，避免被 GC 回收
        self._wndproc_ref = _WNDPROC(self._wnd_proc)
        self._class_atom = 0

        monitor.data_ready.connect(self._on_data)
        theme_manager.theme_changed.connect(self._on_theme_changed)
        settings.setting_changed.connect(self._on_setting_changed)

        # 动画定时器（显示时运行）
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIM_FRAME_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # 任务栏布局/DPI/句柄变化检测
        self._geo_timer = QTimer(self)
        self._geo_timer.setInterval(500)
        self._geo_timer.timeout.connect(self._check_taskbar)
        self._geo_timer.start()

    # ── 对外接口 ──────────────────────────────────────

    def show(self):
        """显示任务栏监控窗口."""
        self._visible = True
        self._ensure_window()
        self._geo_key = self._geometry_key()
        self._refresh_geometry()
        self._render()
        if self._hwnd:
            _user32.ShowWindow(self._hwnd, SW_SHOWNA)
        self._start_animation()

    def hide(self):
        """隐藏任务栏监控窗口."""
        self._visible = False
        self._anim_timer.stop()
        if self._hwnd:
            _user32.ShowWindow(self._hwnd, SW_HIDE)

    @property
    def is_visible(self) -> bool:
        return self._visible

    # ── 任务栏与窗口创建 ──────────────────────────────

    def _find_taskbar(self) -> int | None:
        hwnd = _user32.FindWindowW("Shell_TrayWnd", None)
        return int(hwnd) if hwnd else None

    def _ensure_window(self):
        """确保窗口存在且已嵌入当前任务栏（Explorer 重启后重建）."""
        taskbar = self._find_taskbar()
        if not taskbar:
            return
        stale = (
            self._hwnd is None
            or not _user32.IsWindow(self._hwnd)
            or self._taskbar != taskbar
        )
        if stale:
            self._destroy_window()
            self._create_window(taskbar)

    def _create_window(self, taskbar: int):
        if not self._class_atom:
            self._register_class()
            if not self._class_atom:
                return

        hinst = _kernel32.GetModuleHandleW(None)
        hwnd = _user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            _WINDOW_CLASS, "DX3906 Monitor", WS_POPUP,
            0, 0, 10, 10, None, None, hinst, None)
        if not hwnd:
            return

        # 嵌入任务栏，并补上 WS_CHILD（SetParent 不会修改窗口样式）
        _user32.SetParent(hwnd, taskbar)
        style = _user32.GetWindowLongW(hwnd, GWL_STYLE)
        style = (style | WS_CHILD) & ~WS_POPUP & 0xFFFFFFFF
        _user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        self._hwnd = int(hwnd)
        self._taskbar = taskbar
        self._screen_dc = _user32.GetDC(None)
        self._geo_key = None
        self._layout_key = None
        self._placed = None
        self._dst = None

    def _register_class(self):
        cls = _WNDCLASSW()
        cls.lpfnWndProc = self._wndproc_ref
        cls.hInstance = _kernel32.GetModuleHandleW(None)
        cls.lpszClassName = _WINDOW_CLASS
        self._class_atom = int(_user32.RegisterClassW(ctypes.byref(cls)))

    def _destroy_window(self):
        if self._hwnd and _user32.IsWindow(self._hwnd):
            _user32.DestroyWindow(self._hwnd)
        self._hwnd = None
        self._taskbar = None
        if self._bitmap:
            _gdi32.DeleteObject(self._bitmap)
            self._bitmap = None
        if self._memdc:
            _gdi32.DeleteDC(self._memdc)
            self._memdc = None
        if self._screen_dc:
            _user32.ReleaseDC(None, self._screen_dc)
            self._screen_dc = None
        self._bits = None
        self._image = None
        self._layout_key = None
        self._placed = None
        self._dst = None

    # ── 窗口过程 ──────────────────────────────────────

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_RBUTTONUP:
            self._show_menu()
            return 0
        if msg == WM_LBUTTONDBLCLK:
            if self._on_open_settings:
                self._on_open_settings()
            return 0
        if msg == WM_DESTROY:
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _show_menu(self):
        """任务栏窗口右键菜单."""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b; color: #ffffff;
                border: 1px solid #444; border-radius: 6px;
                padding: 4px 0; font-size: 14px;
            }
            QMenu::item { padding: 8px 32px 8px 20px; }
            QMenu::item:selected { background-color: #3a3a3a; border-radius: 3px; }
            QMenu::separator { height: 1px; background: #444; margin: 4px 12px; }
        """)
        hide_action = menu.addAction("隐藏任务栏监控")
        settings_action = menu.addAction("设置...")
        style_menu = menu.addMenu("任务栏样式")
        for value, label in TASKBAR_STYLE_OPTIONS:
            action = style_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._style == value)
            action.triggered.connect(
                lambda checked, v=value: setattr(
                    self._settings, "taskbar_monitor_style", v))
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        chosen = menu.exec(QCursor.pos())
        if chosen is hide_action:
            self._settings.taskbar_monitor_enabled = False
        elif chosen is settings_action and self._on_open_settings:
            self._on_open_settings()
        elif chosen is quit_action:
            QApplication.instance().quit()

    # ── 数据与主题 ────────────────────────────────────

    def _on_data(self, snapshot: MonitorSnapshot):
        self._cpu = snapshot.cpu_percent
        self._mem = snapshot.memory_percent
        self._up = snapshot.net_sent_bps
        self._down = snapshot.net_recv_bps

    def _on_theme_changed(self, theme: Theme):
        self._theme = theme
        if self._visible:
            self._render()

    def _on_setting_changed(self, key: str, value):
        if key == "monitor_alert_threshold":
            threshold = self._normalise_threshold(value)
            if threshold != self._alert_threshold:
                self._alert_threshold = threshold
                if self._visible:
                    self._render()
            return
        if key != "taskbar_monitor_style":
            return
        style = self._normalise_style(value)
        if style == self._style:
            return
        self._style = style
        if self._visible:
            self._render()

    @staticmethod
    def _normalise_style(value: str) -> str:
        valid = {name for name, _ in TASKBAR_STYLE_OPTIONS}
        return value if value in valid else TASKBAR_STYLE_OPTIONS[0][0]

    @staticmethod
    def _normalise_threshold(value) -> int:
        try:
            return max(1, min(100, int(value)))
        except (TypeError, ValueError):
            return 80

    # ── 数值动画 ──────────────────────────────────────

    def _start_animation(self):
        if not self._anim_timer.isActive():
            self._last_ts = time.monotonic()
            self._anim_timer.start()

    def _on_anim_tick(self):
        now = time.monotonic()
        dt = now - self._last_ts if self._last_ts else ANIM_FRAME_MS / 1000.0
        self._last_ts = now
        dt = max(0.0, min(dt, 0.2))

        # 与帧率无关的指数平滑
        k_pct = 1.0 - math.exp(-dt / _TAU_PERCENT)
        k_spd = 1.0 - math.exp(-dt / _TAU_SPEED)
        self._anim_cpu += (self._cpu - self._anim_cpu) * k_pct
        self._anim_mem += (self._mem - self._anim_mem) * k_pct
        self._anim_up += (self._up - self._anim_up) * k_spd
        self._anim_down += (self._down - self._anim_down) * k_spd

        self._phase = (self._phase + dt / 2.2) % 1.0
        self._flow_phase = (self._flow_phase + dt / 1.1) % 1.0

        # 网速动态上限：立即跟随峰值，缓慢回落（下限 1 KB/s）
        self._up_ceiling = self._advance_ceiling(
            self._up_ceiling, self._up, dt)
        self._down_ceiling = self._advance_ceiling(
            self._down_ceiling, self._down, dt)

        self._render()

    @staticmethod
    def _advance_ceiling(ceiling: float, target: float, dt: float) -> float:
        if target > ceiling:
            return target
        return max(1024.0, ceiling * math.exp(-dt / 2.0))

    def _check_taskbar(self):
        """检测任务栏句柄/位置/DPI 变化，必要时重建或重绘."""
        if not self._visible:
            return
        taskbar = self._find_taskbar()
        if not taskbar:
            return
        if self._taskbar != taskbar or not self._hwnd or not _user32.IsWindow(self._hwnd):
            self._geo_key = None
            self._ensure_window()
            self._refresh_geometry()
            self._render()
            return
        key = self._geometry_key()
        if key != self._geo_key:
            self._geo_key = key
            self._refresh_geometry()
            self._render()

    def _geometry_key(self):
        tr = self._taskbar_rect()
        nr = self._notify_rect()
        sr = self._start_rect()
        dpi = _user32.GetDpiForWindow(self._taskbar) if self._taskbar else 96
        return (tr, nr, sr, dpi)

    def _taskbar_rect(self):
        rect = wintypes.RECT()
        if self._taskbar:
            _user32.GetWindowRect(self._taskbar, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _notify_rect(self):
        if not self._taskbar:
            return (0, 0, 0, 0)
        notify = _user32.FindWindowExW(self._taskbar, None, "TrayNotifyWnd", None)
        rect = wintypes.RECT()
        if notify:
            _user32.GetWindowRect(notify, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _start_rect(self):
        if not self._taskbar:
            return (0, 0, 0, 0)
        start = _user32.FindWindowExW(self._taskbar, None, "Start", None)
        rect = wintypes.RECT()
        if start:
            _user32.GetWindowRect(start, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _refresh_geometry(self):
        """重新计算窗口尺寸与位置（仅布局变化时调用）."""
        if not self._taskbar or not self._hwnd:
            self._dst = None
            return
        tr = self._taskbar_rect()
        tb_h = tr[3] - tr[1]
        dpi = _user32.GetDpiForWindow(self._taskbar) or 96
        if tb_h <= 0:
            self._dst = None
            return

        key = (dpi, tb_h)
        if key != self._layout_key:
            self._layout_key = key
            self._rebuild_surface(dpi, tb_h)
        self._dpi = dpi
        if self._image is None:
            self._dst = None
            return

        pos = self._window_pos()
        if pos is None:
            self._dst = None
            return
        pt = wintypes.POINT(pos[0], pos[1])
        _user32.ScreenToClient(self._taskbar, ctypes.byref(pt))
        self._dst = (pt.x, pt.y)

    # ── 渲染 ──────────────────────────────────────────

    def _render(self):
        if not self._visible or not self._hwnd or not self._taskbar:
            return
        if not _user32.IsWindow(self._hwnd):
            return
        if self._image is None or self._dst is None:
            self._refresh_geometry()
        if self._image is None or self._dst is None:
            return
        self._paint()
        self._blit()

    def _scale(self, dpi: int) -> float:
        return dpi / 96.0

    def _rebuild_surface(self, dpi: int, taskbar_h: int):
        """按 DPI 与任务栏高度重建离屏位图."""
        s = self._scale(dpi)
        font = QFont("Consolas")
        font.setPixelSize(int(round(_FONT_PX * s)))
        font.setBold(True)
        fm = QFontMetricsF(font)

        arrow_w = max(fm.horizontalAdvance("↑"), fm.horizontalAdvance("↓"))
        speed_w = fm.horizontalAdvance("999MB/s")
        label_w = fm.horizontalAdvance("RAM")
        pct_w = fm.horizontalAdvance("100%")

        pad = _PAD_X * s
        pill_pad = _PILL_PAD * s
        # 速度胶囊：箭头 + 网速；百分比胶囊：标签 + 数值
        pill1_w = (arrow_w + _GAP_ARROW * s + speed_w) + pill_pad * 2
        pill2_w = (label_w + _GAP_LABEL * s + pct_w) + pill_pad * 2
        content_w = pill1_w + _PILL_GAP * s + pill2_w
        width = int(round(content_w + pad * 2))
        height = int(round(taskbar_h - _MARGIN_Y * 2 * s))
        if width < 10 or height < 10:
            return

        self._w, self._h = width, height
        self._font = font
        self._cols = (arrow_w, speed_w, label_w, pct_w,
                      pad, pill_pad, pill1_w, pill2_w)

        if self._bitmap:
            _gdi32.DeleteObject(self._bitmap)
        if self._memdc:
            _gdi32.DeleteDC(self._memdc)
        self._memdc = _gdi32.CreateCompatibleDC(self._screen_dc)
        info = _BITMAPINFOHEADER(
            ctypes.sizeof(_BITMAPINFOHEADER), width, -height, 1, 32,
            0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        self._bitmap = _gdi32.CreateDIBSection(
            self._memdc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0)
        _gdi32.SelectObject(self._memdc, self._bitmap)
        self._bits = bits
        self._image = QImage(
            width, height, QImage.Format.Format_ARGB32_Premultiplied)

    def _paint(self):
        theme = self._theme
        neon = QColor(theme.colors.center) if theme else QColor("#00E5FF")
        text = QColor(theme.colors.text) if theme else QColor("#FFFFFF")
        bg = QColor(theme.colors.edge) if theme else QColor("#101020")

        img = self._image
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        s = self._scale(self._dpi)
        radius = _CORNER * s
        rect = QRectF(0.5, 0.5, self._w - 1, self._h - 1)
        if self._style != "minimal":
            bg.setAlpha(205 if self._style == "capsule" else 185)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            if self._style == "flat":
                p.drawRect(rect)
            else:
                p.drawRoundedRect(rect, radius, radius)

            # 边框霓虹呼吸
            breath = 0.5 + 0.5 * math.sin(2 * math.pi * self._phase)
            border = QColor(neon)
            border.setAlpha(int(70 + 80 * breath))
            p.setPen(border)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if self._style == "flat":
                p.drawRect(rect)
            else:
                p.drawRoundedRect(rect, radius, radius)

        p.setFont(self._font)
        (arrow_w, speed_w, label_w, pct_w, pad,
         pill_pad, pill1_w, pill2_w) = self._cols
        row_h = self._h / 2.0
        pill_gap_y = _PILL_GAP_Y * s
        pill_h = row_h - pill_gap_y * 2
        pill_radius = pill_h / 2.0

        # 箭头随数据流动轻微浮动
        wave = math.sin(2 * math.pi * self._flow_phase)
        arrow_dy = 1.2 * s * wave
        speed_base = self._mix(text, neon, 0.2)
        white = QColor("#FFFFFF")
        # 箭头位于同色进度胶囊上，直接使用主题色会在填充区域内失去对比度。
        # 提高亮度并保持完全不透明，再用暗色偏移层勾出轮廓。
        arrow_color = self._mix(neon, white, 0.72)
        arrow_color.setAlpha(255)
        arrow_shadow = QColor(0, 0, 0, 230)
        alert = QColor("#FF4D5D")

        rows = [
            (self._anim_up, self._up_ceiling,
             "CPU", self._anim_cpu, self._cpu, -1),
            (self._anim_down, self._down_ceiling,
             "RAM", self._anim_mem, self._mem, 1),
        ]
        for i, (anim_speed, ceiling, label,
                anim_pct, target_pct, sign) in enumerate(rows):
            top = i * row_h + pill_gap_y

            # ── 网速胶囊（填充比例 = 当前速度 / 动态上限）──
            x1 = pad
            ratio_speed = anim_speed / ceiling if ceiling > 0 else 0.0
            self._draw_pill(
                p, QRectF(x1, top, pill1_w, pill_h), ratio_speed,
                neon, pill_radius)

            x = x1 + pill_pad
            arrow_rect = QRectF(x, top + sign * arrow_dy, arrow_w, pill_h)
            self._draw_network_chevron(
                p, arrow_rect, sign < 0, arrow_color, arrow_shadow)
            x += arrow_w + _GAP_ARROW * s

            speed_flash = self._flash(self._up if sign < 0 else self._down,
                                      anim_speed)
            p.setPen(self._mix(speed_base, white, speed_flash))
            p.drawText(QRectF(x, top, speed_w, pill_h),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _format_speed(anim_speed))

            # ── CPU / RAM 胶囊（填充比例 = 使用率）──
            x2 = x1 + pill1_w + _PILL_GAP * s
            ratio_pct = max(0.0, min(1.0, anim_pct / 100.0))
            metric_color = alert if anim_pct > self._alert_threshold else neon
            self._draw_pill(
                p, QRectF(x2, top, pill2_w, pill_h), ratio_pct,
                metric_color, pill_radius)

            # 警示色只用于进度填充，文字保持高对比度，避免红底上难以阅读。
            p.setPen(text)
            p.drawText(QRectF(x2 + pill_pad, top, label_w, pill_h),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       label)

            pct_flash = min(1.0, abs(target_pct - anim_pct) / 20.0)
            p.setPen(self._mix(neon, white, 0.3 + 0.5 * pct_flash))
            p.drawText(QRectF(x2 + pill2_w - pill_pad - pct_w, top,
                              pct_w, pill_h),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{anim_pct:.0f}%")
        p.end()

    @staticmethod
    def _draw_network_chevron(
            p: QPainter, rect: QRectF, up: bool,
            color: QColor, shadow: QColor):
        """绘制粗线折角上下行图标（^ / v），并用暗色描边提升对比度."""
        inset_x = max(0.8, rect.width() * 0.08)
        # 压低图标高度，避免折角显得细长。
        inset_y = max(2.2, rect.height() * 0.34)
        left = QPointF(rect.left() + inset_x, rect.bottom() - inset_y)
        right = QPointF(rect.right() - inset_x, rect.bottom() - inset_y)
        apex = QPointF(rect.center().x(), rect.top() + inset_y)
        if not up:
            left, right = (
                QPointF(rect.left() + inset_x, rect.top() + inset_y),
                QPointF(rect.right() - inset_x, rect.top() + inset_y),
            )
            apex = QPointF(rect.center().x(), rect.bottom() - inset_y)

        def draw_chevron(pen: QPen, offset: QPointF):
            p.setPen(pen)
            p.drawLine(left + offset, apex + offset)
            p.drawLine(apex + offset, right + offset)

        p.save()
        width = max(2.6, min(3.2, rect.height() * 0.22))
        shadow_pen = QPen(shadow, width + 1.4)
        shadow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        shadow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        draw_chevron(shadow_pen, QPointF(0.8, 0.8))
        color_pen = QPen(color, width)
        color_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        color_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        draw_chevron(color_pen, QPointF(0, 0))
        p.restore()

    def _draw_pill(self, p: QPainter, rect: QRectF, ratio: float,
                   neon: QColor, radius: float):
        """绘制胶囊形进度条：暗色轨道 + 霓虹渐变填充 + 头部亮缘."""
        if self._style == "flat":
            self._draw_flat_bar(p, rect, ratio, neon)
            return
        if self._style == "segments":
            self._draw_segments(p, rect, ratio, neon)
            return
        if self._style == "minimal":
            self._draw_minimal_bar(p, rect, ratio, neon)
            return

        ratio = max(0.0, min(1.0, ratio))
        s = self._scale(self._dpi)

        track = QColor(neon)
        track.setAlpha(22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)
        # 轨道细边，强化“条形”轮廓
        edge = QColor(neon)
        edge.setAlpha(55)
        p.setPen(edge)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius, radius)
        if ratio <= 0.001:
            return

        fill_w = min(rect.width(), max(2.0 * s, rect.width() * ratio))
        fill = QRectF(rect.left(), rect.top(), fill_w, rect.height())
        fill_radius = min(radius, fill_w / 2.0)
        grad = QLinearGradient(fill.left(), 0.0, fill.right(), 0.0)
        c0 = QColor(neon)
        c0.setAlpha(70)
        c1 = QColor(neon)
        c1.setAlpha(190)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(fill, fill_radius, fill_radius)

    def _draw_flat_bar(self, p: QPainter, rect: QRectF, ratio: float,
                       neon: QColor):
        """绘制直角扁平进度条。"""
        ratio = max(0.0, min(1.0, ratio))
        track = QColor(neon)
        track.setAlpha(24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRect(rect)
        if ratio <= 0.001:
            return
        fill = QRectF(rect.left(), rect.top(), rect.width() * ratio, rect.height())
        grad = QLinearGradient(fill.left(), 0.0, fill.right(), 0.0)
        c0 = QColor(neon)
        c0.setAlpha(80)
        c1 = QColor(neon)
        c1.setAlpha(205)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        p.setBrush(grad)
        p.drawRect(fill)

    def _draw_segments(self, p: QPainter, rect: QRectF, ratio: float,
                       neon: QColor):
        """绘制由 8 个格段组成的离散仪表。"""
        ratio = max(0.0, min(1.0, ratio))
        gap = max(1.0, self._scale(self._dpi))
        count = 8
        seg_w = max(1.0, (rect.width() - gap * (count - 1)) / count)
        filled = ratio * count
        for i in range(count):
            x = rect.left() + i * (seg_w + gap)
            color = QColor(neon)
            if i + 1 <= filled:
                color.setAlpha(185)
            elif i < filled:
                color.setAlpha(105)
            else:
                color.setAlpha(28)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, rect.top(), seg_w, rect.height()),
                              2.0, 2.0)

    def _draw_minimal_bar(self, p: QPainter, rect: QRectF, ratio: float,
                          neon: QColor):
        """绘制透明底样式的细线进度提示。"""
        ratio = max(0.0, min(1.0, ratio))
        p.setPen(QColor(neon.red(), neon.green(), neon.blue(), 55))
        p.drawLine(rect.left(), rect.bottom() - 1.0,
                   rect.right(), rect.bottom() - 1.0)
        if ratio > 0.001:
            p.setPen(QColor(neon.red(), neon.green(), neon.blue(), 220))
            p.drawLine(rect.left(), rect.bottom() - 1.0,
                       rect.left() + rect.width() * ratio,
                       rect.bottom() - 1.0)

    @staticmethod
    def _mix(a: QColor, b: QColor, t: float) -> QColor:
        """颜色线性插值，t=0 为 a，t=1 为 b."""
        t = max(0.0, min(1.0, t))
        return QColor(
            int(a.red() + (b.red() - a.red()) * t),
            int(a.green() + (b.green() - a.green()) * t),
            int(a.blue() + (b.blue() - a.blue()) * t))

    @staticmethod
    def _flash(target: float, anim: float) -> float:
        """目标值与动画值差异相对幅度（0~1），用于变化高亮."""
        if target <= 0:
            return 0.0
        return min(1.0, abs(target - anim) / max(target, 1.0))

    def _blit(self):
        """把 QImage 内容提交给 layered 窗口."""
        if not self._bits or self._image is None or self._dst is None:
            return
        size = self._image.sizeInBytes()
        src = (ctypes.c_ubyte * size).from_buffer(self._image.bits())
        ctypes.memmove(self._bits, src, size)

        dst = wintypes.POINT(self._dst[0], self._dst[1])
        src_pt = wintypes.POINT(0, 0)
        size_struct = wintypes.SIZE(self._w, self._h)
        blend = _BLENDFUNCTION(0, 0, 255, AC_SRC_ALPHA)
        _user32.UpdateLayeredWindow(
            self._hwnd, self._screen_dc, ctypes.byref(dst),
            ctypes.byref(size_struct), self._memdc, ctypes.byref(src_pt),
            0, ctypes.byref(blend), ULW_ALPHA)
        placed = (dst.x, dst.y, self._w, self._h)
        if placed != self._placed:
            _user32.SetWindowPos(
                self._hwnd, None, dst.x, dst.y, self._w, self._h,
                SWP_NOZORDER | SWP_NOACTIVATE)
            self._placed = placed

    def _window_pos(self):
        """计算窗口在屏幕上的左上角坐标.

        任务栏图标居中（Win11 默认）时放在「开始」按钮左侧的空白处；
        左对齐或空间不足时回退到通知区左侧.
        """
        tr = self._taskbar_rect()
        nr = self._notify_rect()
        dpi = _user32.GetDpiForWindow(self._taskbar) or 96
        s = self._scale(dpi)
        margin = int(round(2 * s))
        if tr[3] - tr[1] <= tr[2] - tr[0]:
            y = tr[1] + (tr[3] - tr[1] - self._h) // 2
            # 居中任务栏：优先占用开始按钮左侧的空白，避免遮住任务栏图标
            sr = self._start_rect()
            if sr[2] > sr[0]:
                if sr[0] - tr[0] > (tr[2] - tr[0]) // 7:
                    x = sr[0] - self._w - margin
                    if x >= tr[0] + margin:
                        return x, y
            # 回退：贴近通知区左侧
            right = nr[0] if nr[2] > nr[0] else tr[2] - int(round(88 * s))
            return right - self._w - margin, y
        # 垂直任务栏（Win10）：贴底部，居中
        x = tr[1] + (tr[3] - tr[1] - self._w) // 2
        y = tr[3] - self._h - margin
        return x, y
