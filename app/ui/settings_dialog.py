"""设置对话框."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QKeySequenceEdit, QLabel,
    QMessageBox, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
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
        self.setFixedSize(360, 310)
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
        duration_label = QLabel("默认时长（分钟）:")
        duration_label.setFixedWidth(130)
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 120)
        self._duration_spin.setSuffix(" 分钟")
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self._duration_spin)
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
        self._duration_spin.setValue(self._settings.duration_minutes)
        opacity_int = int(self._settings.opacity * 100)
        self._opacity_slider.setValue(opacity_int)
        self._opacity_label.setText(f"{opacity_int}%")
        self._sound_check.setChecked(self._settings.sound_enabled)
        self._hotkey_edit.setKeySequence(QKeySequence(self._settings.hotkey))

    def _on_save(self):
        """保存设置."""
        self._settings.duration_minutes = self._duration_spin.value()
        self._settings.opacity = self._opacity_slider.value() / 100.0
        self._settings.sound_enabled = self._sound_check.isChecked()

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

        self.accept()
