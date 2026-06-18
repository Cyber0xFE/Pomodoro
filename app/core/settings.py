"""设置持久化管理器.

使用 QSettings 在 Windows 注册表中存储用户偏好.
"""

from PySide6.QtCore import QSettings, QObject, Signal

from app.core.constants import DEFAULT_SETTINGS


class SettingsManager(QObject):
    """应用设置管理器.

    信号:
        setting_changed(key, value): 某项设置变更时触发
    """

    setting_changed = Signal(str, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._settings = QSettings("PomodoroApp", "FloatingPomodoro")

    # ── 通用存取 ──────────────────────────────────────

    def get(self, key: str):
        """获取设置值，不存在则返回默认值."""
        default = DEFAULT_SETTINGS.get(key)
        value = self._settings.value(key, default)
        # QSettings 可能返回字符串，需要类型转换
        if default is not None and value is not None:
            try:
                if isinstance(default, bool):
                    return str(value).lower() in ("true", "1", "yes")
                if isinstance(default, float):
                    return float(value)
                if isinstance(default, int):
                    return int(value)
            except (ValueError, TypeError):
                return default
        return value if value is not None else default

    def set(self, key: str, value):
        """设置并持久化."""
        self._settings.setValue(key, value)
        self._settings.sync()
        self.setting_changed.emit(key, value)

    # ── 便捷属性 ──────────────────────────────────────

    @property
    def duration_seconds(self) -> int:
        """总秒数，带旧版 duration_minutes 迁移."""
        value = self._settings.value("duration_seconds")
        if value is not None:
            return int(value)
        # 向后兼容：从旧版 duration_minutes 迁移
        old = self._settings.value("duration_minutes")
        if old is not None:
            return int(old) * 60
        return DEFAULT_SETTINGS["duration_seconds"]

    @duration_seconds.setter
    def duration_seconds(self, value: int):
        self.set("duration_seconds", int(value))

    @property
    def theme(self) -> str:
        return self.get("theme")

    @theme.setter
    def theme(self, value: str):
        self.set("theme", value)

    @property
    def opacity(self) -> float:
        return self.get("opacity")

    @opacity.setter
    def opacity(self, value: float):
        self.set("opacity", value)

    @property
    def window_x(self) -> int:
        return self.get("window_x")

    @window_x.setter
    def window_x(self, value: int):
        self.set("window_x", value)

    @property
    def window_y(self) -> int:
        return self.get("window_y")

    @window_y.setter
    def window_y(self, value: int):
        self.set("window_y", value)

    @property
    def sound_enabled(self) -> bool:
        return self.get("sound_enabled")

    @sound_enabled.setter
    def sound_enabled(self, value: bool):
        self.set("sound_enabled", value)

    @property
    def sound_volume(self) -> float:
        return self.get("sound_volume")

    @sound_volume.setter
    def sound_volume(self, value: float):
        self.set("sound_volume", value)

    @property
    def hotkey(self) -> str:
        return self.get("hotkey")

    @hotkey.setter
    def hotkey(self, value: str):
        self.set("hotkey", value)

    @property
    def hotkey_enabled(self) -> bool:
        return self.get("hotkey_enabled")

    @hotkey_enabled.setter
    def hotkey_enabled(self, value: bool):
        self.set("hotkey_enabled", value)

    @property
    def auto_start(self) -> bool:
        return self.get("auto_start")

    @auto_start.setter
    def auto_start(self, value: bool):
        self.set("auto_start", value)

    @property
    def startup_mode(self) -> str:
        return self.get("startup_mode")

    @startup_mode.setter
    def startup_mode(self, value: str):
        self.set("startup_mode", value)

    @property
    def snap_enabled(self) -> bool:
        return self.get("snap_enabled")

    @snap_enabled.setter
    def snap_enabled(self, value: bool):
        self.set("snap_enabled", value)
