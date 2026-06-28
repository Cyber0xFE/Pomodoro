"""屏幕亮度控制模块.

通过持久化 PowerShell 进程调用 WMI 实现亮度调节，避免反复启动 PowerShell 的开销.

模块维护一个 `BrightnessController` 类，第一次调用时惰性启动后台 PowerShell 进程，
后续亮度设置通过 stdin 快速发送命令（~1ms），同时本地缓存当前亮度值避免反复查询。
"""

import subprocess
import sys
import threading


class BrightnessController:
    """屏幕亮度控制器 — 持久化 PowerShell 进程 + 本地亮度跟踪."""

    def __init__(self):
        self._lock = threading.Lock()
        self._ps: subprocess.Popen | None = None
        self._current: int | None = None  # 本地缓存的当前亮度

    # ── 进程管理 ──────────────────────────────────────

    def _ensure_process(self):
        """惰性启动持久化 PowerShell 进程（仅一次）。"""
        if self._ps is None or self._ps.poll() is not None:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self._ps = subprocess.Popen(
                ["powershell", "-NoLogo", "-NoProfile", "-Command", "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
                text=True,
                bufsize=0,
            )

    def cleanup(self):
        """关闭持久化 PowerShell 进程。"""
        with self._lock:
            if self._ps is not None:
                try:
                    self._ps.stdin.close()
                    self._ps.wait(timeout=3)
                except Exception:
                    if self._ps.poll() is None:
                        self._ps.kill()
                self._ps = None
            self._current = None

    # ── 亮度操作 ──────────────────────────────────────

    def get_brightness(self) -> int | None:
        """获取当前屏幕亮度 (0-100)。

        首次调用通过一次性 PowerShell 查询（首次慢），后续返回本地缓存值。
        返回 None 表示查询失败（可能不支持 WMI 亮度控制）。
        """
        if self._current is not None:
            return self._current

        # 一次性查询初始亮度
        cmd = (
            "Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness "
            "| Select-Object -ExpandProperty CurrentBrightness"
        )
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                ["powershell", "-NoLogo", "-NoProfile", "-Command", cmd],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=flags,
            )
            if result.returncode == 0 and result.stdout.strip():
                self._current = int(result.stdout.strip())
        except Exception:
            pass
        return self._current

    def set_brightness(self, value: int):
        """通过持久化 PowerShell 进程快速设置亮度 (0-100)。"""
        value = max(0, min(100, int(value)))
        with self._lock:
            self._ensure_process()
            cmd = (
                "(Get-WmiObject -Namespace root/wmi "
                "-Class WmiMonitorBrightnessMethods)"
                f".WmiSetBrightness(1, {value})"
            )
            self._ps.stdin.write(cmd + "\n")
            self._ps.stdin.flush()
            self._current = value

    def adjust_brightness(self, delta: int) -> int | None:
        """增减亮度，返回新亮度值或 None。

        Args:
            delta: 变化量（正数增加，负数减少），如 +10、-10

        首次调用会触发一次性 PowerShell 查询（慢），后续通过本地缓存快速调节。
        """
        current = self.get_brightness()
        if current is None:
            return None
        new_value = max(0, min(100, current + delta))
        self.set_brightness(new_value)
        return new_value
