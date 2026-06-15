"""倒计时核心逻辑."""

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.constants import TimerState


class PomodoroTimer(QObject):
    """番茄钟倒计时器.

    信号:
        tick(remaining_sec): 每秒触发，携带剩余秒数
        finished: 倒计时归零时触发
        state_changed(state): 状态变更时触发
    """

    tick = Signal(int)
    finished = Signal()
    state_changed = Signal(TimerState)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._qtimer = QTimer(self)
        self._qtimer.setInterval(1000)
        self._qtimer.timeout.connect(self._on_tick)
        self._remaining = 0
        self._total = 0
        self._state = TimerState.IDLE

    # ── 属性 ──────────────────────────────────────────

    @property
    def state(self) -> TimerState:
        return self._state

    @property
    def remaining(self) -> int:
        return self._remaining

    @property
    def total(self) -> int:
        return self._total

    @property
    def is_running(self) -> bool:
        return self._state == TimerState.RUNNING

    @property
    def fraction_remaining(self) -> float:
        """剩余时间比例 (0.0 ~ 1.0)，用于绘制进度弧线."""
        if self._total <= 0:
            return 0.0
        return self._remaining / self._total

    # ── 操作 ──────────────────────────────────────────

    def set_duration(self, minutes: int):
        """设置倒计时时长，同时重置计时器."""
        self._qtimer.stop()
        self._total = minutes * 60
        self._remaining = self._total
        self._set_state(TimerState.IDLE)
        self.tick.emit(self._remaining)

    def start(self):
        """开始计时."""
        if self._remaining <= 0:
            return
        self._qtimer.start()
        self._set_state(TimerState.RUNNING)

    def pause(self):
        """暂停计时."""
        self._qtimer.stop()
        self._set_state(TimerState.PAUSED)

    def toggle(self):
        """切换 运行/暂停.

        如果计时器已完成（IDLE 且 remaining = 0），则重置到初始时长.
        """
        if self._state == TimerState.RUNNING:
            self.pause()
        elif self._state == TimerState.PAUSED:
            self.start()
        else:
            # IDLE 状态：若剩余时间为 0（已完成），则重置；否则启动
            if self._remaining <= 0:
                self.reset()
            else:
                self.start()

    def reset(self):
        """重置计时器到初始时长."""
        self._qtimer.stop()
        self._remaining = self._total
        self._set_state(TimerState.IDLE)
        self.tick.emit(self._remaining)

    # ── 内部方法 ──────────────────────────────────────

    def _on_tick(self):
        self._remaining -= 1
        self.tick.emit(self._remaining)
        if self._remaining <= 0:
            self._qtimer.stop()
            self._set_state(TimerState.IDLE)
            self.finished.emit()

    def _set_state(self, state: TimerState):
        if self._state != state:
            self._state = state
            self.state_changed.emit(state)
