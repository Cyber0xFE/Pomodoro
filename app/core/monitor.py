"""性能监控数据源 — 轮询 psutil 获取 CPU/内存/网速."""

import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class MonitorSnapshot:
    """单次监控数据快照."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    net_sent_bps: float = 0.0
    net_recv_bps: float = 0.0


class PerformanceMonitor(QObject):
    """性能监控器，定时轮询 psutil 并通过信号发送快照."""

    data_ready = Signal(MonitorSnapshot)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._first_poll = True
        self._prev_sent = 0
        self._prev_recv = 0
        self._prev_time = 0.0

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self):
        self._first_poll = True
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _poll(self):
        import psutil

        # CPU / 内存
        cpu = psutil.cpu_percent(interval=0.0)
        mem = psutil.virtual_memory().percent

        # 网速（diff 累计计数器）
        counters = psutil.net_io_counters()
        now = time.monotonic()

        if self._first_poll:
            sent_bps = 0.0
            recv_bps = 0.0
            self._first_poll = False
        else:
            elapsed = now - self._prev_time
            if elapsed > 0:
                sent_bps = (counters.bytes_sent - self._prev_sent) / elapsed
                recv_bps = (counters.bytes_recv - self._prev_recv) / elapsed
            else:
                sent_bps = 0.0
                recv_bps = 0.0

        self._prev_sent = counters.bytes_sent
        self._prev_recv = counters.bytes_recv
        self._prev_time = now

        self.data_ready.emit(MonitorSnapshot(
            cpu_percent=cpu,
            memory_percent=mem,
            net_sent_bps=sent_bps,
            net_recv_bps=recv_bps,
        ))
