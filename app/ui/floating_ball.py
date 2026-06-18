"""悬浮球主窗口组件 — 赛博科技风格."""

import ctypes
import math
import winsound

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QPointF, Qt, QPoint, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QMouseEvent, QPainter,
    QPainterPath, QPen, QPolygonF, QRadialGradient, QTransform, QWheelEvent, QLinearGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from app.core.constants import (
    BALL_SIZE, OPACITY_MIN, OPACITY_MAX, OPACITY_STEP,
    TimerState, DisplayMode, ANIM_FRAME_MS, ANIM_SMOOTHING,
    SNAP_THRESHOLD, TAIL_WIDTH, BAR_WIDTH,
)
from app.core.timer import PomodoroTimer
from app.core.settings import SettingsManager
from app.core.monitor import PerformanceMonitor, MonitorSnapshot
from app.themes.theme_manager import ThemeManager, Theme
from app.utils.hotkey import MSG, WM_HOTKEY


def _format_time(total_seconds: int) -> str:
    m = total_seconds // 60
    s = total_seconds % 60
    return f"{m:02d}:{s:02d}"


def _format_speed(bps: float) -> str:
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} MB/s"
    elif bps >= 1_000:
        return f"{bps / 1_000:.1f} KB/s"
    return f"{bps:.0f} B/s"


class FloatingBall(QWidget):
    """番茄钟悬浮球 — 赛博科技 HUD 风格."""

    right_clicked = Signal()
    hotkey_pressed = Signal()

    def __init__(
        self,
        timer: PomodoroTimer,
        settings: SettingsManager,
        theme_manager: ThemeManager,
        monitor: PerformanceMonitor,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._timer = timer
        self._settings = settings
        self._theme_manager = theme_manager
        self._monitor = monitor

        self._dragging = False
        self._drag_offset = QPoint()
        self._snapped_edge = None  # 'left' | 'right' | 'top' | 'bottom' | None

        self._ball_diameter = BALL_SIZE
        glow = 20
        win_size = self._ball_diameter + glow * 2
        self.setFixedSize(win_size, win_size)
        self._glow = glow

        # 显示模式
        self._display_mode = DisplayMode.POMODORO

        # 翻转动画
        self._flip_scale = 1.0
        self._monitor_flip_scale = 1.0

        # 监控子视图: "metrics" 或 "network"
        self._monitor_sub = "metrics"

        # 监控目标值
        self._target_cpu = 0.0
        self._target_mem = 0.0
        self._target_net_sent = 0.0
        self._target_net_recv = 0.0

        # 网速动态上限（渐进回落）
        self._net_sent_ceiling = 1024.0
        self._net_recv_ceiling = 1024.0

        # 监控动画插值
        self._anim_cpu = 0.0
        self._anim_mem = 0.0
        self._anim_net_sent = 0.0
        self._anim_net_recv = 0.0
        # 雪佛龙流光相位（随网速推进）
        self._chev_phase_up = 0.0
        self._chev_phase_down = 0.0
        # 水位波纹相位（随 MEM 推进）
        self._ripple_phase = 0.0

        # 动画定时器
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIM_FRAME_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._setup_window()
        self._connect_signals()
        self._apply_theme(theme_manager.current)

    # ── 窗口设置 ──────────────────────────────────────

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)  # 启用鼠标追踪，否则不按按钮时不触发 moveEvent
        self.setWindowOpacity(self._settings.opacity)

    # ── 信号 ──────────────────────────────────────────

    def _connect_signals(self):
        self._timer.tick.connect(self._on_tick)
        self._timer.state_changed.connect(self._on_state_changed)
        self._timer.finished.connect(self._on_finished)
        self._theme_manager.theme_changed.connect(self._apply_theme)
        self._settings.setting_changed.connect(self._on_setting_changed)
        self._monitor.data_ready.connect(self._on_monitor_data)

    @property
    def display_mode(self) -> DisplayMode:
        return self._display_mode

    # Qt property 支持动画
    def get_flip_scale(self) -> float:
        return self._flip_scale

    def set_flip_scale(self, value: float):
        self._flip_scale = value
        self.update()

    flip_scale = Property(float, get_flip_scale, set_flip_scale)

    def get_monitor_flip_scale(self) -> float:
        return self._monitor_flip_scale

    def set_monitor_flip_scale(self, value: float):
        self._monitor_flip_scale = value
        self.update()

    monitor_flip_scale = Property(float, get_monitor_flip_scale, set_monitor_flip_scale)

    def set_display_mode(self, mode: DisplayMode):
        if mode == self._display_mode or getattr(self, '_switching_mode', False):
            return
        self._switching_mode = True
        self._pending_mode = mode

        # 压缩
        self._flip_in = QPropertyAnimation(self, b"flip_scale")
        self._flip_in.setDuration(100)
        self._flip_in.setEasingCurve(QEasingCurve.Type.InQuad)
        self._flip_in.setStartValue(1.0)
        self._flip_in.setEndValue(0.0)
        self._flip_in.finished.connect(self._on_flip_mid)
        self._flip_in.start()

    def _on_flip_mid(self):
        mode = self._pending_mode
        self._display_mode = mode
        if mode == DisplayMode.MONITOR:
            if self._timer.is_running:
                self._timer.pause()
            self._target_cpu = 0.0
            self._target_mem = 0.0
            self._anim_cpu = 0.0
            self._anim_mem = 0.0
            self._target_net_sent = 0.0
            self._target_net_recv = 0.0
            self._chev_phase_up = 0.0
            self._chev_phase_down = 0.0
            self._ripple_phase = 0.0
            self._monitor.start()
            self._anim_timer.start()
        else:
            self._monitor.stop()
            self._anim_timer.stop()
            total = self._timer.total
            self._display_text = _format_time(total) if total > 0 else "--:--"
        self.update()

        # 展开
        self._flip_out = QPropertyAnimation(self, b"flip_scale")
        self._flip_out.setDuration(130)
        self._flip_out.setEasingCurve(QEasingCurve.Type.OutBack)
        self._flip_out.setStartValue(0.0)
        self._flip_out.setEndValue(1.0)
        self._flip_out.finished.connect(self._on_flip_done)
        self._flip_out.start()

    def _on_flip_done(self):
        self._switching_mode = False

    # ── 监控子视图垂直翻页动画 ────────────────────────

    def _start_monitor_flip(self):
        """启动监控子视图垂直翻页动画."""
        if getattr(self, '_sub_flipping', False):
            return
        self._sub_flipping = True

        self._sub_flip_in = QPropertyAnimation(self, b"monitor_flip_scale")
        self._sub_flip_in.setDuration(100)
        self._sub_flip_in.setEasingCurve(QEasingCurve.Type.InQuad)
        self._sub_flip_in.setStartValue(1.0)
        self._sub_flip_in.setEndValue(0.0)
        self._sub_flip_in.finished.connect(self._on_monitor_flip_mid)
        self._sub_flip_in.start()

    def _on_monitor_flip_mid(self):
        self._monitor_sub = "network" if self._monitor_sub == "metrics" else "metrics"
        self.update()

        self._sub_flip_out = QPropertyAnimation(self, b"monitor_flip_scale")
        self._sub_flip_out.setDuration(130)
        self._sub_flip_out.setEasingCurve(QEasingCurve.Type.OutBack)
        self._sub_flip_out.setStartValue(0.0)
        self._sub_flip_out.setEndValue(1.0)
        self._sub_flip_out.finished.connect(self._on_monitor_flip_done)
        self._sub_flip_out.start()

    def _on_monitor_flip_done(self):
        self._sub_flipping = False

    def closeEvent(self, event):
        """关闭时保存位置并隐藏到系统托盘."""
        self._settings.window_x = self.x()
        self._settings.window_y = self.y()
        self.hide()
        event.ignore()

    def nativeEvent(self, event_type: bytes, message_ptr: int) -> tuple[bool, int]:
        """捕获 WM_HOTKEY 全局热键消息."""
        try:
            # PySide6 的 message_ptr 是包装类型，需先 int() 转整数再交给 ctypes
            ptr = ctypes.c_void_p(int(message_ptr))
            msg = ctypes.cast(ptr, ctypes.POINTER(MSG)).contents
            if msg.message == WM_HOTKEY:
                self.hotkey_pressed.emit()
                return True, 0
        except Exception:
            pass
        return super().nativeEvent(event_type, message_ptr)

    # ── 圆形命中测试 ──────────────────────────────────

    def _ball_center(self) -> QPointF:
        g = self._glow
        r = self._ball_diameter / 2.0
        return QPointF(g + r, g + r)

    def _is_inside_ball(self, local_pos: QPoint) -> bool:
        """判断本地坐标是否在球体圆形范围内."""
        center = self._ball_center()
        dx = local_pos.x() - center.x()
        dy = local_pos.y() - center.y()
        r = self._ball_diameter / 2.0
        return (dx * dx + dy * dy) <= (r * r)

    # ── 屏幕边缘吸附 ──────────────────────────────

    def _snap_to_edge(self):
        """拖拽释放时若球体边缘靠近屏幕边缘，则将球体藏到屏幕外，仅留 TAIL_WIDTH px 尾巴。"""
        ball_center = self.frameGeometry().center()
        screen = QApplication.screenAt(ball_center)
        if screen is None:
            screen = QApplication.primaryScreen()

        geo = screen.availableGeometry()
        g = self._glow
        d = self._ball_diameter
        tail = TAIL_WIDTH

        wx = self.x()
        wy = self.y()
        target_x, target_y = wx, wy
        snapped = None

        # 视觉球体的四条边
        ball_left = wx + g
        ball_right = wx + g + d
        ball_top = wy + g
        ball_bottom = wy + g + d

        # 水平：球体左边缘到达/越过屏幕左边缘 → 藏到屏幕外，露尾巴
        if ball_left < geo.left() + SNAP_THRESHOLD:
            target_x = geo.left() + tail - g - d   # 只露右端 tail px
            snapped = 'left'
        elif ball_right > geo.right() - SNAP_THRESHOLD:
            target_x = geo.right() - tail - g       # 只露左端 tail px
            snapped = 'right'

        # 垂直
        if ball_top < geo.top() + SNAP_THRESHOLD:
            target_y = geo.top() + tail - g - d
            if snapped is None:
                snapped = 'top'
        elif ball_bottom > geo.bottom() - SNAP_THRESHOLD:
            target_y = geo.bottom() - tail - g
            if snapped is None:
                snapped = 'bottom'

        if target_x != wx or target_y != wy:
            self.move(target_x, target_y)
            self._settings.window_x = target_x
            self._settings.window_y = target_y
            self._snapped_edge = snapped
            self.update()
        else:
            self._snapped_edge = None

    # ── 吸附条进度指示 ───────────────────────────────

    def _get_snap_progress(self) -> float:
        """获取吸附条的进度值 (0.0~1.0)。"""
        if self._display_mode == DisplayMode.MONITOR:
            if self._monitor_sub == "metrics":
                return self._anim_mem / 100.0
            else:
                return min(self._anim_net_recv / max(self._net_recv_ceiling, 1.0), 1.0)
        else:
            return self._timer.fraction_remaining

    def _paint_snapped_bar(self, painter: QPainter):
        """吸附态绘制 — 赛博 HUD 风格窄条进度指示器."""
        g = self._glow
        d = self._ball_diameter
        tail = TAIL_WIDTH
        bw = BAR_WIDTH
        neon = QColor(self._neon)
        bg = QColor(self._bg)
        edge = self._snapped_edge

        # ── 根据吸附边确定条形区域与方向（窄条居中于尾巴区域内）──
        if edge in ('left', 'right'):
            margin = 8
            bar_center_x = (g + tail / 2) if edge == 'right' else (g + d - tail / 2)
            bar_x = bar_center_x - bw / 2
            bar_w = bw
            bar_h = d - margin * 2
            bar_y = g + margin
            vertical = True
        else:
            margin = 8
            bar_center_y = (g + tail / 2) if edge == 'bottom' else (g + d - tail / 2)
            bar_y = bar_center_y - bw / 2
            bar_h = bw
            bar_w = d - margin * 2
            bar_x = g + margin
            vertical = False

        bar_rect = QRectF(bar_x, bar_y, bar_w, bar_h)
        progress = max(0.0, min(self._get_snap_progress(), 1.0))

        # ── 1. 外层辉光（3 层，与球体一致）──
        for i, alpha in enumerate([20, 38, 58]):
            glow_pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), alpha),
                            3 + i * 2)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            adj = 1.5 + i * 1.5
            painter.drawRoundedRect(bar_rect.adjusted(-adj, -adj, adj, adj), 5 + i, 5 + i)

        # ── 2. 背景 ──
        painter.setPen(Qt.PenStyle.NoPen)
        if vertical:
            bg_grad = QLinearGradient(0, bar_rect.top(), 0, bar_rect.bottom())
        else:
            bg_grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
        bg_grad.setColorAt(0.0, bg.lighter(125))
        bg_grad.setColorAt(0.5, bg)
        bg_grad.setColorAt(1.0, bg.darker(140))
        painter.setBrush(QBrush(bg_grad))
        painter.drawRoundedRect(bar_rect, 3, 3)

        # ── 3. 刻度线 ──
        n_ticks = 5
        tick_color = QColor(neon.red(), neon.green(), neon.blue(), 35)
        painter.setPen(QPen(tick_color, 0.6))
        if vertical:
            for i in range(1, n_ticks + 1):
                ty = bar_y + bar_h * i / (n_ticks + 1)
                painter.drawLine(QPointF(bar_x - 1.5, ty),
                                 QPointF(bar_x + 2, ty))
                painter.drawLine(QPointF(bar_x + bar_w - 2, ty),
                                 QPointF(bar_x + bar_w + 1.5, ty))
        else:
            for i in range(1, n_ticks + 1):
                tx = bar_x + bar_w * i / (n_ticks + 1)
                painter.drawLine(QPointF(tx, bar_y - 1.5),
                                 QPointF(tx, bar_y + 2))
                painter.drawLine(QPointF(tx, bar_y + bar_h - 2),
                                 QPointF(tx, bar_y + bar_h + 1.5))

        # ── 4. 进度填充 ──
        if progress > 0.001:
            pad = 1.2
            if vertical:
                fill_h = max((bar_h - pad * 2) * progress, 2)
                fill_rect = QRectF(bar_x + pad, bar_y + bar_h - pad - fill_h,
                                   bar_w - pad * 2, fill_h)
                fill_grad = QLinearGradient(0, bar_rect.bottom(), 0, bar_rect.top())
            else:
                fill_w = max((bar_w - pad * 2) * progress, 2)
                fill_rect = QRectF(bar_x + pad, bar_y + pad,
                                   fill_w, bar_h - pad * 2)
                fill_grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)

            fill_grad.setColorAt(0.0, QColor(neon.red(), neon.green(), neon.blue(), 180))
            fill_grad.setColorAt(0.15, QColor(
                min(neon.red() + 70, 255),
                min(neon.green() + 70, 255),
                min(neon.blue() + 70, 255), 245))
            fill_grad.setColorAt(0.5, QColor(neon.red(), neon.green(), neon.blue(), 230))
            fill_grad.setColorAt(1.0, QColor(
                max(neon.red() - 30, 0),
                max(neon.green() - 30, 0),
                max(neon.blue() - 30, 0), 200))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_grad))
            painter.drawRoundedRect(fill_rect, 2, 2)

        # ── 5. 边框 ──
        border_pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), 70), 0.8)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bar_rect, 3.5, 3.5)

        # ── 6. 光点 ──
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 45)))
        if vertical:
            painter.drawEllipse(QPointF(bar_rect.center().x(), bar_rect.top() + 3), 1.5, 1.5)
        else:
            painter.drawEllipse(QPointF(bar_rect.left() + 3, bar_rect.center().y()), 1.5, 1.5)

    # ── 事件 ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if not self._is_inside_ball(event.position().toPoint()):
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._did_drag = False
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            event.accept()
            return
        elif event.button() == Qt.MouseButton.MiddleButton:
            new_mode = DisplayMode.MONITOR if self._display_mode == DisplayMode.POMODORO else DisplayMode.POMODORO
            self.set_display_mode(new_mode)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            if not self._did_drag:
                self._did_drag = True
                if self._snapped_edge is not None:
                    self._snapped_edge = None
                    self.update()
            new_pos = event.globalPosition().toPoint() - self._drag_offset

            # 底部边界：禁止球体掉到屏幕工作区下方
            sc = QApplication.screenAt(self.frameGeometry().center())
            if sc is None:
                sc = QApplication.primaryScreen()
            max_y = sc.availableGeometry().bottom() - self._glow - self._ball_diameter
            if new_pos.y() > max_y:
                if self.y() > max_y:
                    # 已吸附在屏幕外 → 允许向上拖回，禁止继续向下
                    new_pos.setY(min(new_pos.y(), self.y()))
                else:
                    new_pos.setY(max_y)

            self.move(new_pos)
            event.accept()
            return
        # 光标反馈（用全局覆盖，无边框窗口的 setCursor 不生效）
        if self._is_inside_ball(event.position().toPoint()):
            QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)
        else:
            QApplication.restoreOverrideCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """鼠标离开窗口时恢复光标."""
        QApplication.restoreOverrideCursor()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging and self._did_drag:
                self._snap_to_edge()
                self._settings.window_x = self.x()
                self._settings.window_y = self.y()
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击：番茄钟模式切换计时，监控模式切换子视图."""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        if not self._is_inside_ball(event.position().toPoint()):
            super().mouseDoubleClickEvent(event)
            return

        if self._display_mode == DisplayMode.MONITOR:
            self._start_monitor_flip()
            event.accept()
            return
        else:
            self._timer.toggle()
            event.accept()
            return

    def wheelEvent(self, event: QWheelEvent):
        if not self._is_inside_ball(event.position().toPoint()):
            event.ignore()
            return
        delta = OPACITY_STEP if event.angleDelta().y() > 0 else -OPACITY_STEP
        new_opacity = max(OPACITY_MIN, min(OPACITY_MAX, self.windowOpacity() + delta))
        self.setWindowOpacity(new_opacity)
        self._settings.opacity = new_opacity
        event.accept()

    # ── 绘制 ──────────────────────────────────────────

    def paintEvent(self, event):
        if not hasattr(self, "_neon") or not hasattr(self, "_display_text"):
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 吸附态 → 条形进度指示器
        if self._snapped_edge is not None:
            self._paint_snapped_bar(painter)
            painter.end()
            return

        # 翻转变换（球心为中心水平缩放）
        if self._flip_scale < 1.0:
            g = self._glow
            r = self._ball_diameter / 2.0
            cx = g + r
            cy = g + r
            t = QTransform()
            t.translate(cx, cy)
            t.scale(self._flip_scale, 1.0)
            t.translate(-cx, -cy)
            painter.setTransform(t)

        if self._display_mode == DisplayMode.MONITOR:
            self._paint_monitor(painter)
        else:
            self._paint_pomodoro(painter)

        painter.end()

    def _paint_pomodoro(self, painter: QPainter):
        g = self._glow
        d = self._ball_diameter
        ball_rect = QRectF(g, g, d, d)
        cx, cy = ball_rect.center().x(), ball_rect.center().y()
        r = d / 2.0

        neon = QColor(self._neon)
        bg = QColor(self._bg)

        # ── 外层辉光 ──
        for i, alpha in enumerate([25, 45, 65]):
            glow_pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), alpha), 6 + i * 4)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ball_rect.adjusted(-2 - i * 2, -2 - i * 2, 2 + i * 2, 2 + i * 2))

        # ── 球体背景 ──
        gradient = QRadialGradient(QPointF(cx - r * 0.15, cy - r * 0.25), r * 1.1)
        gradient.setColorAt(0.0, bg.lighter(130))
        gradient.setColorAt(0.7, bg)
        gradient.setColorAt(1.0, bg.darker(150))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ball_rect)

        # ── 内圈刻度线 ──
        painter.setPen(QPen(QColor(neon.red(), neon.green(), neon.blue(), 35), 1))
        for i in range(12):
            angle = math.radians(i * 30 - 90)
            inner_r = r - 10
            outer_r = r - 5
            x1 = cx + inner_r * math.cos(angle)
            y1 = cy + inner_r * math.sin(angle)
            x2 = cx + outer_r * math.cos(angle)
            y2 = cy + outer_r * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 进度弧线（霓虹发光） ──
        if self._timer.is_running and self._timer.fraction_remaining > 0:
            arc_margin = 6
            arc_rect = QRectF(g + arc_margin, g + arc_margin,
                              d - arc_margin * 2, d - arc_margin * 2)
            span = int(self._timer.fraction_remaining * 360 * 16)

            for layer in range(3):
                glow_alpha = [18, 35, 55][layer]
                glow_w = [8, 5, 3][layer]
                pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), glow_alpha), glow_w)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawArc(arc_rect, 90 * 16, -span)

            pen = QPen(neon, 2.5)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(arc_rect, 90 * 16, -span)

        # ── 时间文字 ──
        tf = self._fonts.time
        font = QFont(tf.family, tf.size)
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(font)

        text_rect = QRectF(0, 0, self.width(), self.height() - 10)

        for i, alpha in enumerate([35, 20, 12]):
            glow_c = QColor(neon.red(), neon.green(), neon.blue(), alpha)
            painter.setPen(glow_c)
            off = i + 1
            painter.drawText(text_rect.translated(off, 0), Qt.AlignmentFlag.AlignCenter, self._display_text)
            painter.drawText(text_rect.translated(-off, 0), Qt.AlignmentFlag.AlignCenter, self._display_text)
            painter.drawText(text_rect.translated(0, off), Qt.AlignmentFlag.AlignCenter, self._display_text)
            painter.drawText(text_rect.translated(0, -off), Qt.AlignmentFlag.AlignCenter, self._display_text)

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._display_text)

        # ── 状态指示 ──
        sf = self._fonts.state
        state_font = QFont(sf.family, sf.size)
        painter.setFont(state_font)
        painter.setPen(QColor(neon.red(), neon.green(), neon.blue(), 150))
        state_text = self._get_state_text()
        state_rect = QRectF(0, self.height() / 2 + 10, self.width(), 16)
        painter.drawText(state_rect, Qt.AlignmentFlag.AlignCenter, state_text)

        # ── 顶部光点 ──
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.drawEllipse(QPointF(cx - r * 0.3, cy - r * 0.35), 3, 3)

    def _paint_monitor(self, painter: QPainter):
        g = self._glow
        d = self._ball_diameter
        ball_rect = QRectF(g, g, d, d)
        cx, cy = ball_rect.center().x(), ball_rect.center().y()
        r = d / 2.0

        neon = QColor(self._neon)
        bg = QColor(self._bg)

        # ── 外层辉光（不受翻页影响） ──
        for i, alpha in enumerate([25, 45, 65]):
            glow_pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), alpha), 6 + i * 4)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ball_rect.adjusted(-2 - i * 2, -2 - i * 2, 2 + i * 2, 2 + i * 2))

        # ── 球心区域垂直翻页 ──
        painter.save()
        if self._monitor_flip_scale < 1.0:
            t = QTransform()
            t.translate(cx, cy)
            t.scale(1.0, self._monitor_flip_scale)
            t.translate(-cx, -cy)
            painter.setTransform(t, True)

        # ── 球体背景 ──
        gradient = QRadialGradient(QPointF(cx - r * 0.15, cy - r * 0.25), r * 1.1)
        gradient.setColorAt(0.0, bg.lighter(130))
        gradient.setColorAt(0.7, bg)
        gradient.setColorAt(1.0, bg.darker(150))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(ball_rect)

        # ── 顶部光点 ──
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.drawEllipse(QPointF(cx - r * 0.3, cy - r * 0.35), 3, 3)

        if self._monitor_sub == "metrics":
            self._paint_monitor_metrics(painter, g, d, cx, cy, r, neon, bg, ball_rect)
        else:
            self._paint_monitor_network(painter, cx, cy, r, neon)

        painter.restore()

    def _paint_monitor_metrics(self, painter, g, d, cx, cy, r, neon, bg, ball_rect):
        """监控子视图：CPU 弧线 + 内存水位线."""

        # ── 内存水位线 ──
        mem_pct = self._anim_mem / 100.0
        if mem_pct > 0:
            painter.save()
            ball_clip = QPainterPath()
            ball_clip.addEllipse(ball_rect)
            painter.setClipPath(ball_clip)

            water_top = cy + r - (2 * r * mem_pct)
            ripple_amp = 4.0 * math.sqrt(max(mem_pct, 0.01))
            wave_len = r * 2.5             # 波长
            n_pts = 40                     # 采样点数
            # 水面路径：上边为正弦波纹，下边到底部
            left = g
            right = g + d
            bottom = cy + r + g + 10
            wave_path = QPainterPath()
            wave_path.moveTo(left, bottom)
            wave_path.lineTo(right, bottom)
            for i in range(n_pts, -1, -1):
                px = left + (i / n_pts) * d
                py = water_top + ripple_amp * math.sin(
                    2 * math.pi * (self._ripple_phase + px / wave_len))
                wave_path.lineTo(px, py)
            wave_path.closeSubpath()

            water_grad = QLinearGradient(0, cy + r, 0, water_top)
            water_grad.setColorAt(0.0, QColor(neon.red(), neon.green(), neon.blue(), 60))
            water_grad.setColorAt(0.3, QColor(neon.red(), neon.green(), neon.blue(), 100))
            water_grad.setColorAt(0.9, QColor(neon.red(), neon.green(), neon.blue(), 160))
            water_grad.setColorAt(1.0, QColor(neon.red(), neon.green(), neon.blue(), 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(water_grad))
            painter.drawPath(wave_path)

            painter.restore()

        # ── 内圈刻度线 ──
        painter.setPen(QPen(QColor(neon.red(), neon.green(), neon.blue(), 25), 1))
        for i in range(12):
            angle = math.radians(i * 30 - 90)
            x1 = cx + (r - 10) * math.cos(angle)
            y1 = cy + (r - 10) * math.sin(angle)
            x2 = cx + (r - 5) * math.cos(angle)
            y2 = cy + (r - 5) * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── CPU 进度弧线 ──
        cpu_pct = self._anim_cpu / 100.0
        arc_margin = 6
        arc_rect = QRectF(g + arc_margin, g + arc_margin,
                          d - arc_margin * 2, d - arc_margin * 2)
        span = int(cpu_pct * 360 * 16)

        for layer in range(3):
            glow_alpha = [18, 35, 55][layer]
            glow_w = [8, 5, 3][layer]
            pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), glow_alpha), glow_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(arc_rect, 90 * 16, -span)

        pen = QPen(neon, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, 90 * 16, -span)

        # ── CPU / MEM 文字 ──
        label_font = QFont(self._fonts.state.family, 14)
        label_font.setBold(True)
        painter.setFont(label_font)

        cpu_text = f"CPU {int(self._anim_cpu)}%"
        painter.setPen(QColor(255, 255, 255, 240))
        cpu_rect = QRectF(cx - 50, cy - 26, 100, 22)
        painter.drawText(cpu_rect, Qt.AlignmentFlag.AlignCenter, cpu_text)

        mem_text = f"MEM {int(self._anim_mem)}%"
        painter.setPen(QColor(255, 255, 255, 240))
        mem_rect = QRectF(cx - 50, cy + 6, 100, 22)
        painter.drawText(mem_rect, Qt.AlignmentFlag.AlignCenter, mem_text)

        # ── 双击切换提示 ──
        hint_font = QFont(self._fonts.state.family, 7)
        painter.setFont(hint_font)
        painter.setPen(QColor(neon.red(), neon.green(), neon.blue(), 80))
        hint_rect = QRectF(cx - 40, cy + r * 0.65, 80, 12)
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, "双击查看网速")

    def _fit_font(self, family: str, size: int, text: str, max_width: int) -> QFont:
        """返回加粗字体，必要时逐号缩小使 text 宽度不超过 max_width（下限 7）。"""
        s = size
        while s > 7:
            f = QFont(family, s)
            f.setBold(True)
            if QFontMetrics(f).horizontalAdvance(text) <= max_width:
                return f
            s -= 1
        f = QFont(family, max(s, 7))
        f.setBold(True)
        return f

    def _paint_monitor_network(self, painter, cx, cy, r, neon):
        """监控子视图：网速 — 上传弧线 + 下载水位线."""

        ball_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        g = self._glow
        d = self._ball_diameter

        # ── 下载水位线 ──
        recv_ceil = max(self._net_recv_ceiling, 1.0)
        recv_pct = min(self._anim_net_recv / recv_ceil, 1.0)
        if recv_pct > 0.01:
            painter.save()
            ball_clip = QPainterPath()
            ball_clip.addEllipse(ball_rect)
            painter.setClipPath(ball_clip)

            water_top = cy + r - (2 * r * recv_pct)
            water_rect = QRectF(ball_rect.left(), water_top, r * 2, cy + r - water_top + ball_rect.top())

            water_grad = QLinearGradient(0, cy + r, 0, water_top)
            water_grad.setColorAt(0.0, QColor(neon.red(), neon.green(), neon.blue(), 60))
            water_grad.setColorAt(0.3, QColor(neon.red(), neon.green(), neon.blue(), 100))
            water_grad.setColorAt(0.9, QColor(neon.red(), neon.green(), neon.blue(), 160))
            water_grad.setColorAt(1.0, QColor(neon.red(), neon.green(), neon.blue(), 220))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(water_grad))
            painter.drawRect(water_rect)

            painter.restore()

        # ── 内圈刻度线 ──
        painter.setPen(QPen(QColor(neon.red(), neon.green(), neon.blue(), 25), 1))
        for i in range(12):
            angle = math.radians(i * 30 - 90)
            inner_r = r - 10
            outer_r = r - 5
            x1 = cx + inner_r * math.cos(angle)
            y1 = cy + inner_r * math.sin(angle)
            x2 = cx + outer_r * math.cos(angle)
            y2 = cy + outer_r * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 上传进度弧线 ──
        sent_ceil = max(self._net_sent_ceiling, 1.0)
        sent_pct = min(self._anim_net_sent / sent_ceil, 1.0)
        arc_margin = 6
        arc_rect = QRectF(g + arc_margin, g + arc_margin,
                          d - arc_margin * 2, d - arc_margin * 2)
        span = int(sent_pct * 360 * 16)

        for layer in range(3):
            glow_alpha = [18, 35, 55][layer]
            glow_w = [8, 5, 3][layer]
            pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), glow_alpha), glow_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(arc_rect, 90 * 16, -span)

        pen = QPen(neon, 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(arc_rect, 90 * 16, -span)

        # ── 上下层背景图案：叠加雪佛龙(chevron)指示上传(上)/下载(下)，流速驱动流光 ──
        cw, ch = r * 0.32, r * 0.16      # 雪佛龙半宽 / 高度
        widths = (1.5, 2.5, 4.0)         # 由细到粗
        n = 3
        base_a, amp_a = 105, 90          # 透明度基线 / 流光幅度
        # 上传：上半三道朝上雪佛龙，亮峰向上游动
        for i, yb in enumerate((cy - r * 0.62, cy - r * 0.50, cy - r * 0.38)):
            a = int(max(0, min(255, base_a + amp_a * math.sin(
                2 * math.pi * self._chev_phase_up + i * 2 * math.pi / n))))
            pen = QPen(QColor(255, 255, 255, a), widths[i])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([
                QPointF(cx - cw, yb), QPointF(cx, yb - ch), QPointF(cx + cw, yb),
            ]))
        # 下载：下半三道朝下雪佛龙，亮峰向下游动
        for i, yb in enumerate((cy + r * 0.38, cy + r * 0.50, cy + r * 0.62)):
            a = int(max(0, min(255, base_a + amp_a * math.sin(
                2 * math.pi * self._chev_phase_down - i * 2 * math.pi / n))))
            pen = QPen(QColor(neon.red(), neon.green(), neon.blue(), a), widths[i])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF([
                QPointF(cx - cw, yb), QPointF(cx, yb + ch), QPointF(cx + cw, yb),
            ]))

        # ── 上传 / 下载文字 ──
        # 行中心偏离圆心 ±10px，圆在该处变窄，按可用宽度自动缩放字号防止溢出球外
        row_half_w = math.sqrt(max(r * r - 12 * 12, 1.0))
        avail_w = int(row_half_w * 2 - 8)

        up_text = _format_speed(self._anim_net_sent)
        up_font = self._fit_font(self._fonts.state.family, 14, up_text, avail_w)
        painter.setFont(up_font)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(QRectF(cx - row_half_w, cy - 20, row_half_w * 2, 20),
                         Qt.AlignmentFlag.AlignCenter, up_text)

        down_text = _format_speed(self._anim_net_recv)
        down_font = self._fit_font(self._fonts.state.family, 14, down_text, avail_w)
        painter.setFont(down_font)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.drawText(QRectF(cx - row_half_w, cy, row_half_w * 2, 20),
                         Qt.AlignmentFlag.AlignCenter, down_text)

        # ── 双击切换提示 ──
        hint_font = QFont(self._fonts.state.family, 7)
        painter.setFont(hint_font)
        painter.setPen(QColor(neon.red(), neon.green(), neon.blue(), 80))
        hint_rect = QRectF(cx - 40, cy + r * 0.65, 80, 12)
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, "双击查看指标")

    # ── 回调 ──────────────────────────────────────────

    def _on_tick(self, remaining: int):
        if self._display_mode != DisplayMode.POMODORO:
            return
        self._display_text = _format_time(remaining)
        self.update()

    def _on_state_changed(self, state: TimerState):
        if self._display_mode != DisplayMode.POMODORO:
            return
        if state == TimerState.IDLE:
            total = self._timer.total
            self._display_text = _format_time(total) if total > 0 else "--:--"
        self.update()

    def _on_finished(self):
        if self._display_mode != DisplayMode.POMODORO:
            return
        self._display_text = "✓"
        self.update()
        if self._settings.sound_enabled:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
        self._flash_animation = QPropertyAnimation(self, b"windowOpacity")
        self._flash_animation.setDuration(400)
        self._flash_animation.setLoopCount(5)
        self._flash_animation.setStartValue(1.0)
        self._flash_animation.setEndValue(0.2)
        self._flash_animation.finished.connect(self._on_flash_finished)
        self._flash_animation.start()

    def _on_monitor_data(self, snapshot: MonitorSnapshot):
        self._target_cpu = snapshot.cpu_percent
        self._target_mem = snapshot.memory_percent
        self._target_net_sent = snapshot.net_sent_bps
        self._target_net_recv = snapshot.net_recv_bps

        # 动态上限：快速上升
        if snapshot.net_sent_bps > self._net_sent_ceiling:
            self._net_sent_ceiling = snapshot.net_sent_bps
        if snapshot.net_recv_bps > self._net_recv_ceiling:
            self._net_recv_ceiling = snapshot.net_recv_bps

    def _on_anim_tick(self):
        s = ANIM_SMOOTHING
        self._anim_cpu += (self._target_cpu - self._anim_cpu) * s
        self._anim_mem += (self._target_mem - self._anim_mem) * s
        self._anim_net_sent += (self._target_net_sent - self._anim_net_sent) * s
        self._anim_net_recv += (self._target_net_recv - self._anim_net_recv) * s

        # 雪佛龙流光：相位随当前网速推进（0.2~2.0 周/秒），越快越快
        dt = ANIM_FRAME_MS / 1000.0
        sent_pct = min(self._anim_net_sent / max(self._net_sent_ceiling, 1.0), 1.0)
        recv_pct = min(self._anim_net_recv / max(self._net_recv_ceiling, 1.0), 1.0)
        self._chev_phase_up = (self._chev_phase_up + (0.2 + 1.8 * sent_pct) * dt) % 1.0
        self._chev_phase_down = (self._chev_phase_down + (0.2 + 1.8 * recv_pct) * dt) % 1.0
        # 水位波纹：相位随 MEM 推进（0.15~1.2 周/秒），越高越快
        mem_pct = min(self._anim_mem / 100.0, 1.0)
        self._ripple_phase = (self._ripple_phase + (0.15 + 1.05 * mem_pct) * dt) % 1.0

        # 动态上限：缓慢回落（0.5%/帧 ≈ 15%/秒），下限 1 KB/s
        decay = 0.995
        min_ceil = 1024.0
        if self._target_net_sent < self._net_sent_ceiling * 0.5:
            self._net_sent_ceiling = max(self._net_sent_ceiling * decay, min_ceil)
        if self._target_net_recv < self._net_recv_ceiling * 0.5:
            self._net_recv_ceiling = max(self._net_recv_ceiling * decay, min_ceil)

        self.update()

    def _on_flash_finished(self):
        self.setWindowOpacity(self._settings.opacity)

    def _on_setting_changed(self, key: str, value):
        if key == "opacity":
            self.setWindowOpacity(value)

    def _apply_theme(self, theme: Theme | None):
        if theme is None:
            return
        self._neon = theme.colors.center
        self._bg = QColor(theme.colors.edge)
        self._fonts = theme.fonts
        if self._display_mode == DisplayMode.POMODORO:
            total = self._timer.total
            self._display_text = _format_time(total) if total > 0 else "--:--"
        self.update()

    def _get_state_text(self) -> str:
        state = self._timer.state
        if state == TimerState.RUNNING:
            return "● ACTIVE"
        elif state == TimerState.PAUSED:
            return "◉ PAUSED"
        # 倒计时结束显示 ✓ 时 → DONE；否则就绪态 → STANDBY
        if self._display_text == "✓":
            return "◎ DONE"
        return "◎ STANDBY"
