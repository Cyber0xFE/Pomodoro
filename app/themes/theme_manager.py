"""主题数据类与主题管理器."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal


@dataclass
class ThemeColors:
    """主题配色."""
    center: str = "#E74C3C"
    edge: str = "#F1948A"
    progress_arc: str = "rgba(255,255,255,200)"
    text: str = "#ffffff"
    text_shadow: str = "rgba(0,0,0,80)"
    button_hover: str = "rgba(255,255,255,30)"


@dataclass
class ThemeFont:
    """字体配置."""
    family: str = "Segoe UI"
    size: int = 18
    bold: bool = True


@dataclass
class ThemeFonts:
    """字体集合."""
    time: ThemeFont = field(default_factory=lambda: ThemeFont(size=18, bold=True))
    state: ThemeFont = field(default_factory=lambda: ThemeFont(size=9, bold=False))


@dataclass
class ThemeBall:
    """悬浮球外观配置."""
    size: int = 120
    shadow_enabled: bool = True
    shadow_color: str = "rgba(0,0,0,60)"
    shadow_blur: int = 15


@dataclass
class Theme:
    """完整主题定义."""
    name: str = "Classic"
    colors: ThemeColors = field(default_factory=ThemeColors)
    fonts: ThemeFonts = field(default_factory=ThemeFonts)
    ball: ThemeBall = field(default_factory=ThemeBall)

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        """从字典创建主题."""
        colors_data = data.get("colors", {})
        colors = ThemeColors(
            center=colors_data.get("center", "#E74C3C"),
            edge=colors_data.get("edge", "#F1948A"),
            progress_arc=colors_data.get("progress_arc", "rgba(255,255,255,200)"),
            text=colors_data.get("text", "#ffffff"),
            text_shadow=colors_data.get("text_shadow", "rgba(0,0,0,80)"),
            button_hover=colors_data.get("button_hover", "rgba(255,255,255,30)"),
        )

        fonts_data = data.get("fonts", {})
        time_font = fonts_data.get("time", {})
        state_font = fonts_data.get("state", {})
        fonts = ThemeFonts(
            time=ThemeFont(
                family=time_font.get("family", "Segoe UI"),
                size=time_font.get("size", 18),
                bold=time_font.get("bold", True),
            ),
            state=ThemeFont(
                family=state_font.get("family", "Segoe UI"),
                size=state_font.get("size", 9),
                bold=state_font.get("bold", False),
            ),
        )

        ball_data = data.get("ball", {})
        ball = ThemeBall(
            size=ball_data.get("size", 120),
            shadow_enabled=ball_data.get("shadow_enabled", True),
            shadow_color=ball_data.get("shadow_color", "rgba(0,0,0,60)"),
            shadow_blur=ball_data.get("shadow_blur", 15),
        )

        return cls(
            name=data.get("name", "Classic"),
            colors=colors,
            fonts=fonts,
            ball=ball,
        )


class ThemeManager(QObject):
    """主题管理器.

    信号:
        theme_changed(Theme): 主题切换时触发
    """

    theme_changed = Signal(Theme)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._themes: dict[str, Theme] = {}
        self._current: Theme | None = None
        self._load_builtin_themes()

    # ── 属性 ──────────────────────────────────────────

    @property
    def current(self) -> Theme | None:
        return self._current

    @property
    def theme_names(self) -> list[str]:
        return list(self._themes.keys())

    # ── 操作 ──────────────────────────────────────────

    def apply(self, name: str):
        """应用指定主题（不存在则回退到第一个可用主题）."""
        theme = self._themes.get(name)
        if theme is None and self._themes:
            theme = next(iter(self._themes.values()))
        if theme is None:
            return
        self._current = theme
        self.theme_changed.emit(self._current)

    def get_theme(self, name: str) -> Theme | None:
        return self._themes.get(name)

    # ── 内部方法 ──────────────────────────────────────

    def _load_builtin_themes(self):
        """加载 presets 目录下所有 JSON 主题文件."""
        presets_dir = Path(__file__).parent / "presets"
        if not presets_dir.exists():
            return
        for json_file in sorted(presets_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                theme = Theme.from_dict(data)
                self._themes[theme.name] = theme
            except (json.JSONDecodeError, KeyError) as e:
                print(f"加载主题失败 {json_file}: {e}")
