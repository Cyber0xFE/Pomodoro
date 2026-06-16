# 🍅 PomodoroBall — 番茄钟悬浮球

一个赛博 HUD 风格的 Windows 桌面番茄钟应用，以圆形悬浮球形式始终置顶显示。

![Python](https://img.shields.io/badge/Python-3.12-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-green)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2B-lightgrey)

## ✨ 特性

- **始终置顶悬浮球** — 半透明圆形窗口，不遮挡工作区域，鼠标穿透透明区域
- **赛博 HUD 风格** — 霓虹光晕、进度弧线、刻度标记，5 套主题皮肤可选
- **番茄钟核心功能** — 默认 25 分钟，支持秒级精度设置，开始/暂停/重置，完成时响铃提示
- **性能监控模式** — CPU 弧线 + 内存水位线 + 实时网速，中键点击切换
- **过场动画** — 模式切换时水平翻转变脸动画，平滑过渡
- **右键菜单操作** — 切换时长/模式、更换皮肤、打开设置
- **拖拽移动** — 任意拖动到屏幕合适位置
- **滚轮调透明度** — 鼠标滚轮即可调整悬浮球透明度
- **双击切换** — 双击悬浮球快速开始/暂停计时

## 🎨 主题皮肤

| 主题 | 主色调 |
|------|--------|
| **Neon Cyan** 🏷️ 默认 | `#00F0FF` 霓虹青 |
| Matrix | `#00FF41` 矩阵绿 |
| Ghost White | `#C0C0C0` 幽灵白 |
| Synthwave | `#FF007F` 合成波粉 |
| Amber Terminal | `#FFB000` 琥珀橙 |

## 🚀 快速开始

### 环境要求

- Windows 10+
- Python 3.12+

### 安装依赖

```bash
pip install pyside6 psutil
```

### 运行开发版

```bash
python main.py
```

### 打包为 EXE

```bash
# 生成图标（可选，仓库已包含）
python generate_icon.py

# 打包
pyinstaller --onefile --noconsole --name "PomodoroBall" \
  --icon "app/assets/icons/pomodoro.ico" \
  --add-data "app/themes/presets/*.json;app/themes/presets/" \
  --add-data "app/assets/icons/pomodoro.ico;app/assets/icons/" \
  main.py
```

输出文件：`dist/PomodoroBall.exe`（约 48MB，单文件，无需安装）

## 🎮 操作指南

| 操作 | 功能 |
|------|------|
| **双击** 悬浮球 | 开始 / 暂停计时（番茄钟模式） |
| **中键** 悬浮球 | 切换 番茄钟 / 性能监控 模式 |
| **右键** 悬浮球 | 弹出菜单（设置时长、换肤、切换模式、退出等） |
| **拖拽** 悬浮球 | 移动位置 |
| **滚轮** 在球体上 | 调整透明度 |

## 📁 项目结构

```
Pomodoro/
├── main.py                     # 入口文件
├── generate_icon.py            # 图标生成脚本
├── app/
│   ├── app.py                  # PomodoroApp 主控制器
│   ├── core/
│   │   ├── constants.py        # 枚举、默认值、常量
│   │   ├── timer.py            # PomodoroTimer 倒计时引擎
│   │   ├── monitor.py          # PerformanceMonitor 性能数据源
│   │   └── settings.py         # SettingsManager (QSettings 持久化)
│   ├── themes/
│   │   ├── theme_manager.py    # 主题管理器
│   │   └── presets/            # 5 套 JSON 主题预设
│   ├── ui/
│   │   ├── floating_ball.py    # 悬浮球窗口（QPainter 自绘）
│   │   ├── context_menu.py     # 右键菜单
│   │   └── settings_dialog.py  # 设置对话框
│   └── utils/
│       ├── screen_utils.py     # 屏幕工具
│       └── single_instance.py  # 单实例检测
└── app/assets/
    └── icons/
        └── pomodoro.ico        # 应用图标
```

## 🔧 技术栈

- **GUI 框架**: PySide6 (Qt for Python)
- **系统监控**: psutil（CPU / 内存 / 网络）
- **渲染**: QPainter 自定义绘制（无边框圆形窗口）
- **打包**: PyInstaller（单文件 EXE）
- **持久化**: QSettings（Windows 注册表）
- **主题系统**: JSON 预设 + 运行时切换

## 📝 License

MIT
