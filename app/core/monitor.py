"""性能监控数据源 — 轮询 psutil 和 Windows PDH 获取系统指标.

GPU 和磁盘指标使用 Windows 自带的 Performance Data Helper (PDH) 计数器。
PDH 不可用（例如非 Windows 系统或没有对应驱动计数器）时，快照中的字段为
``None``，由展示层显示为不可用，而不是把缺少数据误报成 0%。
"""

import ctypes
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass
class MonitorSnapshot:
    """单次监控数据快照."""
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    net_sent_bps: float = 0.0
    net_recv_bps: float = 0.0
    # PDH 数据缺失时为 None；0.0 表示计数器可用且当前确实空闲。
    gpu_percent: float | None = None
    disk_percent: float | None = None


def _clamp_percent(value: float) -> float:
    """将系统计数器值限制为百分比范围，并处理驱动偶发的异常值."""
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _gpu_utilization(values: Iterable[tuple[str, float]]) -> float | None:
    """Return busiest physical GPU utilization from GPU Engine samples.

    GPU Engine instance names contain an optional ``pid_<n>_`` prefix followed
    by ``luid_<id>_phys_<n>_eng_<type>_<n>``. Values from several processes
    sharing one physical engine are summed (and capped at 100), then the
    busiest engine on each adapter and the busiest adapter are selected.
    """
    by_adapter: dict[str, dict[str, float]] = defaultdict(dict)
    for name, raw_value in values:
        try:
            value = _clamp_percent(raw_value)
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        # Usually "pid_123_luid_0x..._phys_0_eng_3D_0". Ignore the optional
        # process prefix so all processes on one physical adapter are summed.
        # LUIDs may contain several underscore-separated hexadecimal parts
        # (for example ``luid_0x00000000_0x000100B9_phys_0``), so capture
        # lazily through the physical-adapter marker rather than one token.
        match = re.search(r"(luid_.*?_phys_[^_]+)_eng_(.+)$", name, re.IGNORECASE)
        if match:
            adapter, engine = match.group(1), match.group(2)
        else:
            adapter, engine = "_unknown", name
        by_adapter[adapter][engine] = min(
            100.0, value + by_adapter[adapter].get(engine, 0.0))

    if not by_adapter:
        return None
    return _clamp_percent(max(max(engines.values()) for engines in by_adapter.values()))


def _disk_utilization(values: Iterable[tuple[str, float]]) -> float | None:
    """Return busiest physical disk activity from ``% Idle Time`` samples."""
    activity: list[float] = []
    total_idle: float | None = None
    for name, raw_idle in values:
        try:
            idle = _clamp_percent(raw_idle)
        except (TypeError, ValueError):
            continue
        if str(name).strip().lower() == "_total":
            total_idle = idle
        else:
            activity.append(100.0 - idle)
    if activity:
        return _clamp_percent(max(activity))
    if total_idle is not None:
        return _clamp_percent(100.0 - total_idle)
    return None


_PDH_ERROR_SUCCESS = 0
_PDH_MORE_DATA = 0x800007D2
_PDH_FMT_DOUBLE = 0x00000200
_PDH_FMT_NOCAP100 = 0x00008000


class _PdhCounterValue(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_uint32),
        ("value", ctypes.c_double),
    ]


class _PdhCounterItem(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_wchar_p),
        ("formatted", _PdhCounterValue),
    ]


class _WindowsPerformanceCounters:
    """Small PDH wrapper for wildcard GPU Engine and PhysicalDisk counters."""

    _GPU_PATH = r"\GPU Engine(*)\Utilization Percentage"
    _DISK_PATH = r"\PhysicalDisk(*)\% Idle Time"

    def __init__(self):
        self._query = None
        self._gpu_counter = None
        self._disk_counter = None
        self._primed = False
        self._pdh = None

    @property
    def available(self) -> bool:
        return self._query is not None

    def start(self):
        self.stop()
        if os.name != "nt":
            return
        try:
            self._pdh = ctypes.WinDLL("pdh.dll")
            open_query = self._pdh.PdhOpenQueryW
            open_query.argtypes = [ctypes.c_wchar_p, ctypes.c_uint64,
                                   ctypes.POINTER(ctypes.c_void_p)]
            open_query.restype = ctypes.c_uint32
            add_counter = getattr(self._pdh, "PdhAddEnglishCounterW",
                                  self._pdh.PdhAddCounterW)
            add_counter.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                    ctypes.c_uint64, ctypes.POINTER(ctypes.c_void_p)]
            add_counter.restype = ctypes.c_uint32
            collect = self._pdh.PdhCollectQueryData
            collect.argtypes = [ctypes.c_void_p]
            collect.restype = ctypes.c_uint32
            format_array = self._pdh.PdhGetFormattedCounterArrayW
            format_array.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_void_p,
            ]
            format_array.restype = ctypes.c_uint32
            close_query = self._pdh.PdhCloseQuery
            close_query.argtypes = [ctypes.c_void_p]
            close_query.restype = ctypes.c_uint32

            query = ctypes.c_void_p()
            if open_query(None, 0, ctypes.byref(query)) != _PDH_ERROR_SUCCESS:
                return
            gpu = ctypes.c_void_p()
            disk = ctypes.c_void_p()
            gpu_status = add_counter(query, self._GPU_PATH, 0, ctypes.byref(gpu))
            disk_status = add_counter(query, self._DISK_PATH, 0, ctypes.byref(disk))
            # Keep either counter when available.  A machine can expose disk
            # counters while lacking WDDM GPU counters, or vice versa.
            self._query = query
            self._gpu_counter = gpu if gpu_status == _PDH_ERROR_SUCCESS else None
            self._disk_counter = disk if disk_status == _PDH_ERROR_SUCCESS else None
            if self._gpu_counter is None and self._disk_counter is None:
                self.stop()
                return
            collect(query)  # first sample establishes the PDH baseline
            self._primed = True
        except (AttributeError, OSError, TypeError):
            self.stop()

    def stop(self):
        if self._query is not None and self._pdh is not None:
            try:
                self._pdh.PdhCloseQuery(self._query)
            except (AttributeError, OSError):
                pass
        self._query = None
        self._gpu_counter = None
        self._disk_counter = None
        self._primed = False

    def sample(self) -> tuple[float | None, float | None]:
        """Collect one sample and return ``(gpu_percent, disk_percent)``."""
        if self._query is None or self._pdh is None:
            return None, None
        try:
            status = self._pdh.PdhCollectQueryData(self._query)
            if status != _PDH_ERROR_SUCCESS or not self._primed:
                self._primed = True
                return None, None
            gpu = self._read_counter(self._gpu_counter, _gpu_utilization)
            disk = self._read_counter(self._disk_counter, _disk_utilization)
            return gpu, disk
        except (AttributeError, OSError, TypeError, ValueError):
            return None, None

    def _read_counter(self, counter, reducer):
        if counter is None:
            return None
        size = ctypes.c_uint32(0)
        count = ctypes.c_uint32(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            counter, _PDH_FMT_DOUBLE | _PDH_FMT_NOCAP100,
            ctypes.byref(size), ctypes.byref(count), None)
        if status != _PDH_MORE_DATA or size.value == 0:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        item_count = ctypes.c_uint32(0)
        status = self._pdh.PdhGetFormattedCounterArrayW(
            counter, _PDH_FMT_DOUBLE | _PDH_FMT_NOCAP100,
            ctypes.byref(size), ctypes.byref(item_count),
            ctypes.cast(buffer, ctypes.c_void_p))
        if status != _PDH_ERROR_SUCCESS or item_count.value == 0:
            return None
        array_type = _PdhCounterItem * item_count.value
        items = ctypes.cast(buffer, ctypes.POINTER(array_type)).contents
        return reducer((item.name, item.formatted.value)
                       for item in items if item.formatted.status == 0)


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
        self._hardware = _WindowsPerformanceCounters()

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self):
        self._first_poll = True
        self._hardware.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._hardware.stop()

    def set_interval(self, ms: int):
        """设置轮询间隔（毫秒）.

        所有指标共用此定时器；网速按实际经过时间求商，
        因此间隔变更不影响速率计算，仅改变数据更新频率.
        """
        self._timer.setInterval(int(ms))

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

        gpu, disk = self._hardware.sample()

        self.data_ready.emit(MonitorSnapshot(
            cpu_percent=cpu,
            memory_percent=mem,
            net_sent_bps=sent_bps,
            net_recv_bps=recv_bps,
            gpu_percent=gpu,
            disk_percent=disk,
        ))
