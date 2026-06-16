# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Windows 桌面番茄钟 / 性能监控应用，核心为一个赛博 HUD 风格的圆形悬浮球，始终置顶显示。PySide6 + Python + psutil 实现，PyInstaller 打包为单文件 EXE。

两种显示模式：**番茄钟**（倒计时 + 进度弧线）和 **性能监控**（CPU 弧线 + 内存水位线 + 实时网速），中键点击或右键菜单切换，水平翻转变脸动画过渡。

## 常用命令

```bash
# 运行开发版
python main.py

# 生成应用图标（修改 generate_icon.py 后）
python generate_icon.py

# 打包为 EXE（单文件、无控制台、嵌入图标、含主题数据文件）
pyinstaller --onefile --noconsole --name "PomodoroBall" \
  --icon "app/assets/icons/pomodoro.ico" \
  --add-data "app/themes/presets/*.json;app/themes/presets/" \
  main.py

# 清理构建缓存（必要时）
rm -rf build dist PomodoroBall.spec
```

## 架构

单进程 PySide6 应用，通过 Qt 信号/槽机制通信（无 IPC）。

```
main.py                     # 入口
app/app.py                  # PomodoroApp：组装模块、恢复设置、启动
  ├── core/timer.py         # PomodoroTimer：QTimer 倒计时引擎，set_duration 接收秒
  ├── core/monitor.py       # PerformanceMonitor：psutil 轮询 CPU/内存/网速
  ├── core/settings.py      # SettingsManager：QSettings → Windows 注册表，duration_seconds 带旧版兼容迁移
  ├── core/constants.py     # TimerState / DisplayMode 枚举、BALL_SIZE、DEFAULT_SETTINGS
  ├── themes/theme_manager.py  # ThemeManager：加载 JSON 预设，切换主题
  │   └── presets/*.json    # 5 套赛博霓虹主题
  ├── ui/floating_ball.py   # FloatingBall：圆形无边框窗口，QPainter 自绘
  ├── ui/context_menu.py    # 右键菜单
  └── ui/settings_dialog.py # 设置对话框（分钟+秒双微调框）
      utils/                # screen_utils、single_instance
```

### 模块关系

- `PomodoroApp` 持有 `PomodoroTimer`、`PerformanceMonitor`、`SettingsManager`、`ThemeManager`、`FloatingBall`、`ContextMenu`
- `FloatingBall` 通过信号连接到 timer（`tick`、`finished`、`state_changed`）、monitor（`data_ready`）、settings（`setting_changed`）、theme_manager（`theme_changed`）
- `ContextMenu` 操作直接调用 timer/settings/theme_manager 方法
- `DisplayMode` 枚举控制 `FloatingBall` 的渲染分支：`POMODORO`（倒计时视图）和 `MONITOR`（性能监控视图）

### 主题系统

`center` 字段为霓虹主色，`edge` 字段为深色背景色。`FloatingBall._apply_theme` 将它们分别映射到 `self._neon` 和 `self._bg`。主题名不在预设中的回退到第一个可用主题。

### FloatingBall 渲染要点

- 窗口标志：`FramelessWindowHint | WindowStaysOnTopHint | Tool`
- 不使用 `setMask`（会产生锯齿），而是在 `mousePressEvent`/`wheelEvent` 中通过 `_is_inside_ball()` 手动判断圆形区域命中，透明区域穿透
- `setMouseTracking(True)` + `QApplication.setOverrideCursor` 实现悬停光标切换
- `mouseReleaseEvent` 中拖动距离 < 10px 才算点击（但单击不触发计时，仅记录；双击由 `mouseDoubleClickEvent` 触发 `toggle`）
- 两种绘制路径：`_paint_pomodoro` 和 `_paint_monitor`，通过 `_display_mode` 分支
- 模式切换时使用水平翻转变脸动画（`_flip_animation` QVariantAnimation，0→1 时中点切换内容）

### 性能监控模式

- `PerformanceMonitor`（`core/monitor.py`）每秒轮询 psutil，通过 `data_ready` 信号发送 `MonitorSnapshot`
- CPU：弧形进度条，EMA 平滑动画
- 内存：水位线填充效果，从底部向上
- 网速：上行/下行实时数字显示，动态调整上限
- 中键点击悬浮球切换 POMODORO ↔ MONITOR

### 时长系统

- 统一以**秒**为内部单位：`DEFAULT_SETTINGS["duration_seconds"]`（1500 = 25 分钟）、`SettingsManager.duration_seconds`、`PomodoroTimer.set_duration(total_seconds)`
- 向后兼容：`SettingsManager.duration_seconds` getter 在找不到新键 `duration_seconds` 时回退读旧键 `duration_minutes` 并 `×60` 自动迁移
- 设置对话框使用分钟+秒两个 QSpinBox，保存时合并为总秒数
- 预设菜单（DURATION_OPTIONS）仍保持分钟语义，调用侧 `×60` 转换
- 显示层 `_format_time(seconds)` 始终输出 `MM:SS`

### 打包注意事项

- `--add-data` 的分隔符在 Windows 上是 `;`（不是 `:`）
- 修改源码后 PyInstaller 会自动检测变更并增量重建，修改图标需清理 build/dist 缓存
- Windows 任务栏图标缓存需重启 explorer.exe 刷新
