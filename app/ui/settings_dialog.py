"""设置对话框."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QKeySequenceEdit,
    QLabel, QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout,
    QWidget,
)

from app.core.constants import OPACITY_MIN, OPACITY_MAX
from app.core.settings import SettingsManager


class _HotkeyEdit(QKeySequenceEdit):
    """自定义热键输入框：Backspace / Esc 清空，拒绝无修饰键的单键输入."""

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        # Backspace / Delete / Esc → 清空
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete, Qt.Key.Key_Escape):
            self.clear()
            return
        # 单独按下修饰键不录入
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                   Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        super().keyPressEvent(event)


class SettingsDialog(QDialog):
    """番茄钟设置对话框."""

    def __init__(self, settings: SettingsManager, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = settings

        self.setWindowTitle("番茄钟设置")
        self.setFixedSize(390, 560)
        self.setStyleSheet("font-size: 14px;")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self._build_ui()
        self._load_current_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 16, 20, 16)

        # ── 时长设置 ──
        duration_layout = QHBoxLayout()
        duration_label = QLabel("默认时长:")
        duration_label.setFixedWidth(130)
        self._duration_min_spin = QSpinBox()
        self._duration_min_spin.setRange(0, 120)
        self._duration_min_spin.setSuffix(" 分钟")
        self._duration_min_spin.setFixedWidth(105)
        self._duration_sec_spin = QSpinBox()
        self._duration_sec_spin.setRange(0, 59)
        self._duration_sec_spin.setSuffix(" 秒")
        self._duration_sec_spin.setFixedWidth(90)
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self._duration_min_spin)
        duration_layout.addWidget(self._duration_sec_spin)
        duration_layout.addStretch()
        layout.addLayout(duration_layout)

        # ── 透明度 ──
        opacity_layout = QHBoxLayout()
        opacity_label = QLabel("透明度:")
        opacity_label.setFixedWidth(130)
        self._opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self._opacity_slider.setRange(int(OPACITY_MIN * 100), int(OPACITY_MAX * 100))
        self._opacity_label = QLabel()
        self._opacity_label.setFixedWidth(32)
        self._opacity_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        opacity_layout.addWidget(opacity_label)
        opacity_layout.addWidget(self._opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        layout.addLayout(opacity_layout)

        self._opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )

        # ── 声音开关 ──
        self._sound_check = QCheckBox("计时结束时播放提示音")
        layout.addWidget(self._sound_check)

        # ── 屏幕边缘吸附 ──
        self._snap_check = QCheckBox("拖拽到屏幕边缘时自动吸附隐藏")
        layout.addWidget(self._snap_check)

        # ── 皮肤轮播 ──
        self._theme_cycle_check = QCheckBox("自动轮播皮肤（每 30 秒切换一次）")
        layout.addWidget(self._theme_cycle_check)

        # ── 开机启动 ──
        self._autostart_check = QCheckBox("开机自动启动")
        layout.addWidget(self._autostart_check)

        # ── 默认启动模式 ──
        mode_layout = QHBoxLayout()
        mode_label = QLabel("默认启动模式:")
        mode_label.setFixedWidth(130)
        self._startup_mode_combo = QComboBox()
        self._startup_mode_combo.addItem("番茄钟", "pomodoro")
        self._startup_mode_combo.addItem("性能监控", "monitor")
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self._startup_mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # ── 全局热键 ──
        hotkey_layout = QHBoxLayout()
        hotkey_label = QLabel("显示/隐藏热键:")
        hotkey_label.setFixedWidth(130)
        self._hotkey_edit = _HotkeyEdit()
        self._hotkey_edit.setMaximumSequenceLength(1)
        self._hotkey_edit.setToolTip("点击后按下组合键，如 Ctrl+Shift+F11\n" +
                                     "Backspace / Esc 可清空")
        hotkey_layout.addWidget(hotkey_label)
        hotkey_layout.addWidget(self._hotkey_edit)
        layout.addLayout(hotkey_layout)

        # ── 亮度增加热键 ──
        bup_layout = QHBoxLayout()
        bup_label = QLabel("亮度增加热键:")
        bup_label.setFixedWidth(130)
        self._brightness_up_edit = _HotkeyEdit()
        self._brightness_up_edit.setMaximumSequenceLength(1)
        self._brightness_up_edit.setToolTip(
            "点击后按下组合键，如 Ctrl+Alt+Up\nBackspace / Esc 可清空")
        bup_layout.addWidget(bup_label)
        bup_layout.addWidget(self._brightness_up_edit)
        layout.addLayout(bup_layout)

        # ── 亮度降低热键 ──
        bdn_layout = QHBoxLayout()
        bdn_label = QLabel("亮度降低热键:")
        bdn_label.setFixedWidth(130)
        self._brightness_down_edit = _HotkeyEdit()
        self._brightness_down_edit.setMaximumSequenceLength(1)
        self._brightness_down_edit.setToolTip(
            "点击后按下组合键，如 Ctrl+Alt+Down\nBackspace / Esc 可清空")
        bdn_layout.addWidget(bdn_label)
        bdn_layout.addWidget(self._brightness_down_edit)
        layout.addLayout(bdn_layout)

        # ── 亮度步长 ──
        step_layout = QHBoxLayout()
        step_label = QLabel("亮度调节步长:")
        step_label.setFixedWidth(130)
        self._brightness_step_spin = QSpinBox()
        self._brightness_step_spin.setRange(5, 25)
        self._brightness_step_spin.setSuffix(" %")
        self._brightness_step_spin.setFixedWidth(105)
        step_layout.addWidget(step_label)
        step_layout.addWidget(self._brightness_step_spin)
        step_layout.addStretch()
        layout.addLayout(step_layout)

        layout.addStretch()

        # ── 按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def _load_current_values(self):
        """从 SettingsManager 加载当前值."""
        total = self._settings.duration_seconds
        self._duration_min_spin.setValue(total // 60)
        self._duration_sec_spin.setValue(total % 60)
        opacity_int = int(self._settings.opacity * 100)
        self._opacity_slider.setValue(opacity_int)
        self._opacity_label.setText(f"{opacity_int}%")
        self._sound_check.setChecked(self._settings.sound_enabled)
        self._snap_check.setChecked(self._settings.snap_enabled)
        self._theme_cycle_check.setChecked(self._settings.theme_cycle_enabled)
        self._autostart_check.setChecked(self._settings.auto_start)
        idx = self._startup_mode_combo.findData(self._settings.startup_mode)
        if idx >= 0:
            self._startup_mode_combo.setCurrentIndex(idx)
        self._hotkey_edit.setKeySequence(QKeySequence(self._settings.hotkey))
        self._brightness_up_edit.setKeySequence(
            QKeySequence(self._settings.brightness_up_hotkey))
        self._brightness_down_edit.setKeySequence(
            QKeySequence(self._settings.brightness_down_hotkey))
        self._brightness_step_spin.setValue(self._settings.brightness_step)

    def _on_save(self):
        """保存设置."""
        total = self._duration_min_spin.value() * 60 + self._duration_sec_spin.value()
        if total <= 0:
            total = 60  # 至少 1 分钟
        self._settings.duration_seconds = total
        self._settings.opacity = self._opacity_slider.value() / 100.0
        self._settings.sound_enabled = self._sound_check.isChecked()
        self._settings.snap_enabled = self._snap_check.isChecked()
        self._settings.theme_cycle_enabled = self._theme_cycle_check.isChecked()
        self._settings.auto_start = self._autostart_check.isChecked()
        self._settings.startup_mode = self._startup_mode_combo.currentData()

        # 保存热键 — 必须有修饰键
        ks = self._hotkey_edit.keySequence()
        if ks.isEmpty():
            self._settings.hotkey_enabled = False
            self._settings.hotkey = ""
        else:
            hotkey_str = ks.toString(QKeySequence.SequenceFormat.PortableText)
            if "+" not in hotkey_str:
                QMessageBox.warning(
                    self, "无效热键",
                    f"「{hotkey_str}」缺少修饰键（Ctrl/Shift/Alt/Win），\n"
                    "请使用组合键，例如 Ctrl+Shift+F11。")
                return
            self._settings.hotkey = hotkey_str
            self._settings.hotkey_enabled = True

        # ── 保存亮度热键 ──
        # 亮度增加热键
        ks_up = self._brightness_up_edit.keySequence()
        if ks_up.isEmpty():
            self._settings.brightness_up_hotkey = ""
        else:
            hotkey_str = ks_up.toString(QKeySequence.SequenceFormat.PortableText)
            if "+" not in hotkey_str:
                QMessageBox.warning(
                    self, "无效热键",
                    f"亮度增加热键「{hotkey_str}」缺少修饰键"
                    "（Ctrl/Shift/Alt/Win），\n"
                    "请使用组合键，例如 Ctrl+Alt+Up。")
                return
            self._settings.brightness_up_hotkey = hotkey_str

        # 亮度降低热键
        ks_dn = self._brightness_down_edit.keySequence()
        if ks_dn.isEmpty():
            self._settings.brightness_down_hotkey = ""
        else:
            hotkey_str = ks_dn.toString(QKeySequence.SequenceFormat.PortableText)
            if "+" not in hotkey_str:
                QMessageBox.warning(
                    self, "无效热键",
                    f"亮度降低热键「{hotkey_str}」缺少修饰键"
                    "（Ctrl/Shift/Alt/Win），\n"
                    "请使用组合键，例如 Ctrl+Alt+Down。")
                return
            self._settings.brightness_down_hotkey = hotkey_str

        # 至少有一个亮度热键配置才启用
        self._settings.brightness_hotkey_enabled = bool(
            self._settings.brightness_up_hotkey
            or self._settings.brightness_down_hotkey)

        # 亮度步长
        self._settings.brightness_step = self._brightness_step_spin.value()

        self.accept()
