"""在独立进程读取任务栏按钮，主线程只消费布局快照。"""

import base64
import json
import math
import os
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


# UI Automation 可能等待 Explorer 或本应用响应窗口消息，因此只允许在
# 可终止的辅助进程中调用。编码脚本直接随 Python 模块打包，无需额外资源。
_PROBE_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class TaskbarNative {
    [DllImport("user32.dll")]
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")]
    public static extern bool IsWindow(IntPtr hwnd);
}
'@
[void][TaskbarNative]::SetThreadDpiAwarenessContext([IntPtr](-4))
$handle = [IntPtr](__HANDLE__)
$condition = New-Object System.Windows.Automation.OrCondition -ArgumentList @(
    (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Button)),
    (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::SplitButton)),
    (New-Object System.Windows.Automation.PropertyCondition -ArgumentList @(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit))
)
while ([TaskbarNative]::IsWindow($handle)) {
    try {
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $bounds = $root.Current.BoundingRectangle
        $controls = $root.FindAll(
            [System.Windows.Automation.TreeScope]::Descendants, $condition)
        $rects = @()
        for ($i = 0; $i -lt $controls.Count; $i++) {
            $control = $controls.Item($i)
            if ($control.Current.IsOffscreen) { continue }
            $r = $control.Current.BoundingRectangle
            if ($r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0) { continue }
            if ($r.Bottom -le $bounds.Top -or $r.Top -ge $bounds.Bottom) { continue }
            # 归一化坐标避免跨进程 DPI 感知模式不同造成二次缩放。
            $rects += ,@(
                (($r.Left - $bounds.Left) / $bounds.Width),
                (($r.Top - $bounds.Top) / $bounds.Height),
                (($r.Right - $bounds.Left) / $bounds.Width),
                (($r.Bottom - $bounds.Top) / $bounds.Height))
        }
        $result = @{ handle = $handle.ToInt64(); rects = $rects; ok = ($rects.Count -gt 0) }
        [Console]::WriteLine(($result | ConvertTo-Json -Compress -Depth 4))
        [Console]::Out.Flush()
    } catch {
        [Console]::WriteLine('{"ok":false}')
        [Console]::Out.Flush()
    }
    Start-Sleep -Milliseconds 1000
}
"""


def free_taskbar_position(taskbar, occupied, width, height, margin, previous=None):
    """合并占用区间，优先沿用安全位置，否则选择最大空档。"""
    left, top, right, bottom = taskbar
    horizontal = right - left >= bottom - top
    start, end = (left, right) if horizontal else (top, bottom)
    length = width if horizontal else height
    intervals = []
    for x1, y1, x2, y2 in occupied:
        if x2 <= left or x1 >= right or y2 <= top or y1 >= bottom:
            continue
        a, b = (x1, x2) if horizontal else (y1, y2)
        intervals.append((max(start, a - margin), min(end, b + margin)))

    gaps = []
    cursor = start + margin
    for a, b in sorted(intervals):
        if a - cursor >= length:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if end - margin - cursor >= length:
        gaps.append((cursor, end - margin))
    if not gaps:
        return None

    axis = previous[0 if horizontal else 1] if previous else None
    if axis is None or not any(a <= axis and axis + length <= b for a, b in gaps):
        a, b = max(gaps, key=lambda gap: gap[1] - gap[0])
        axis = b - length
    if horizontal:
        if height > bottom - top:
            return None
        return axis, top + (bottom - top - height) // 2
    if width > right - left:
        return None
    return left + (right - left - width) // 2, axis


class TaskbarLayoutProbe(QObject):
    """异步接收布局；暂时不可读时保留缓存，无响应时使其失效。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.readyReadStandardError.connect(self._discard_error)
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(500)
        self._watchdog.timeout.connect(self._check_timeout)
        self._handle = None
        self._rects = None
        self._snapshot_geometry = None
        self._received = 0.0
        self._started = 0.0
        self._retry_after = 0.0
        self._buffer = b""

    def start(self, handle):
        if handle != self._handle:
            self.stop()
            self._handle = handle
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return
        if time.monotonic() < self._retry_after:
            return
        source = _PROBE_SCRIPT.replace('__HANDLE__', str(int(handle)))
        encoded = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        program = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                               'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
        self._buffer = b""
        self._rects = None
        self._snapshot_geometry = None
        self._received = 0.0
        self._started = time.monotonic()
        self._retry_after = self._started + 10.0
        self._process.start(program, ['-NoProfile', '-NonInteractive',
                                      '-EncodedCommand', encoded])
        self._watchdog.start()

    def stop(self):
        self._watchdog.stop()
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
        self._handle = None
        self._rects = None
        self._snapshot_geometry = None
        self._received = 0.0
        self._retry_after = 0.0
        self._buffer = b""

    def rectangles(self, handle, taskbar):
        if handle != self._handle or self._rects is None:
            return None
        if time.monotonic() - self._received > 4.0:
            return None
        if self._snapshot_geometry is None:
            self._snapshot_geometry = taskbar
        elif self._snapshot_geometry != taskbar:
            # 旧布局只可用于原来的任务栏几何，避免屏幕/DPI 变化后误用。
            self.invalidate()
            return None
        left, top, right, bottom = taskbar
        width, height = right - left, bottom - top
        return [(left + math.floor(a * width), top + math.floor(b * height),
                 left + math.ceil(c * width), top + math.ceil(d * height))
                for a, b, c, d in self._rects]

    def invalidate(self):
        self._rects = None
        self._snapshot_geometry = None

    def _read_output(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        while b'\n' in self._buffer:
            line, self._buffer = self._buffer.split(b'\n', 1)
            try:
                result = json.loads(line)
                if result.get('handle', self._handle) != self._handle:
                    continue
                if result.get('ok'):
                    rects = result['rects']
                    if not rects or not all(
                            len(r) == 4 and all(isinstance(n, (int, float)) and
                                                math.isfinite(n) for n in r)
                            and r[2] > r[0] and r[3] > r[1] for r in rects):
                        raise ValueError('Invalid taskbar rectangles')
                    self._rects = tuple(tuple(r) for r in rects)
                    self._snapshot_geometry = None
                # 开始菜单、搜索等弹层可能让 UIA 暂时返回空树。
                # 这代表检测进程仍在响应，并不代表已确认的空档消失。
                # 保留最近一次有效布局，等待下一次成功扫描再更新位置。
                self._received = time.monotonic()
                self.changed.emit()
            except (ValueError, TypeError, KeyError):
                continue

    def _discard_error(self):
        self._process.readAllStandardError()

    def _check_timeout(self):
        now = time.monotonic()
        if now - (self._received or self._started) > 4.0:
            self._process.kill()
            self.invalidate()
            self._received = 0.0
            self._retry_after = now + 10.0
            self._watchdog.stop()
            self.changed.emit()
