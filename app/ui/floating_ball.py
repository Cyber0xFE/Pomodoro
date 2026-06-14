"""悬浮球主窗口组件 — 赛博科技风格."""

import math
import winsound

from PySide6.QtCore import QPropertyAnimation, QPointF, Qt, QPoint, QRectF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QMouseEvent, QPainter,
    QPen, QRadialGradient, QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from app.core.constants import BALL_SIZE, OPACITY_MIN, OPACITY_MAX, OPACITY_STEP, TimerState
from app.core.timer import PomodoroTimer
from app.core.settings import SettingsManager
from app.themes.theme_manager import ThemeManager, Theme


def _format_time(total_seconds: int) -> str:
    m = total_seconds // 60
    s = total_seconds % 60
    return f"{m:02d}:{s:02d}"


class FloatingBall(QWidget):
    """番茄钟悬浮球 — 赛博科技 HUD 风格."""

    right_clicked = Signal()

    def __init__(
        self,
        timer: PomodoroTimer,
        settings: SettingsManager,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._timer = timer
        self._settings = settings
        self._theme_manager = theme_manager

        self._dragging = False
        self._drag_offset = QPoint()

        self._ball_diameter = BALL_SIZE
        glow = 20
        win_size = self._ball_diameter + glow * 2
        self.setFixedSize(win_size, win_size)
        self._glow = glow

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

    # ── 事件 ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if not self._is_inside_ball(event.position().toPoint()):
            event.ignore()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
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
            if self._dragging:
                delta = (event.globalPosition().toPoint()
                         - self.frameGeometry().topLeft()
                         - self._drag_offset)
                # 拖动了才保存位置
                if delta.manhattanLength() >= 10:
                    self._settings.window_x = self.x()
                    self._settings.window_y = self.y()
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击切换 开始/暂停."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_inside_ball(event.position().toPoint()):
                self._timer.toggle()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

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

        # 霓虹光晕
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

        painter.end()

    # ── 回调 ──────────────────────────────────────────

    def _on_tick(self, remaining: int):
        self._display_text = _format_time(remaining)
        self.update()

    def _on_state_changed(self, state: TimerState):
        if state == TimerState.IDLE:
            total = self._timer.total
            self._display_text = _format_time(total) if total > 0 else "--:--"
        self.update()

    def _on_finished(self):
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
        total = self._timer.total
        self._display_text = _format_time(total) if total > 0 else "--:--"
        self.update()

    def _get_state_text(self) -> str:
        state = self._timer.state
        if state == TimerState.RUNNING:
            return "● ACTIVE"
        elif state == TimerState.PAUSED:
            return "◉ PAUSED"
        return "◎ STANDBY"
