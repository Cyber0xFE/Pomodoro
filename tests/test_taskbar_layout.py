import json
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEventLoop, QProcess, QTimer

from app.utils.taskbar_layout import TaskbarLayoutProbe, free_taskbar_position


class FreeTaskbarPositionTests(unittest.TestCase):
    def assert_clear(self, position, width, height, rectangles):
        self.assertIsNotNone(position)
        x, y = position
        for a, b, c, d in rectangles:
            self.assertFalse(x < c and x + width > a and y < d and y + height > b)

    def test_left_aligned_uses_gap_before_weather(self):
        taskbar = (0, 1824, 3072, 1920)
        # 左侧应用、右侧天气、通知区分别独立占用任务栏。
        occupied = [(0, 1824, 1526, 1920), (2032, 1824, 2336, 1920),
                    (2360, 1824, 3072, 1920)]
        position = free_taskbar_position(taskbar, occupied, 327, 88, 8)
        self.assert_clear(position, 327, 88, occupied)
        self.assertGreaterEqual(position[0], 1526 + 8)
        self.assertLessEqual(position[0] + 327, 2032 - 8)

    def test_centered_uses_left_gap_and_avoids_widgets(self):
        occupied = [(12, 1824, 316, 1920), (674, 1824, 2180, 1920),
                    (2296, 1824, 3072, 1920)]
        position = free_taskbar_position((0, 1824, 3072, 1920), occupied, 327, 88, 8)
        self.assert_clear(position, 327, 88, occupied)
        self.assertLess(position[0], 674)

    def test_layout_change_moves_monitor_then_restores_after_crowding(self):
        taskbar = (0, 0, 1000, 48)
        occupied = [(0, 0, 400, 48), (800, 0, 1000, 48)]
        first = free_taskbar_position(taskbar, occupied, 164, 44, 4)
        self.assertEqual(free_taskbar_position(
            taskbar, occupied, 164, 44, 4, first), first)
        moved = [(0, 0, 200, 48), (600, 0, 1000, 48)]
        second = free_taskbar_position(taskbar, moved, 164, 44, 4, first)
        self.assert_clear(second, 164, 44, moved)
        self.assertNotEqual(second, first)
        self.assertIsNone(free_taskbar_position(
            taskbar, [(0, 0, 900, 48)], 164, 44, 4, second))
        self.assertIsNotNone(free_taskbar_position(taskbar, occupied, 164, 44, 4))

    def test_overlapping_buttons_and_negative_monitor_coordinates(self):
        occupied = [(-1920, 0, -1500, 48), (-1700, 0, -1300, 48),
                    (-400, 0, 0, 48)]
        position = free_taskbar_position((-1920, 0, 0, 48), occupied, 164, 44, 4)
        self.assert_clear(position, 164, 44, occupied)
        self.assertLess(position[0], 0)

    def test_vertical_taskbar_checks_width(self):
        taskbar = (0, 0, 80, 1000)
        occupied = [(0, 0, 80, 300), (0, 800, 80, 1000)]
        self.assert_clear(free_taskbar_position(taskbar, occupied, 70, 50, 4),
                          70, 50, occupied)
        self.assertIsNone(free_taskbar_position(taskbar, occupied, 164, 44, 4))


class TaskbarLayoutProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_normalized_rectangles_map_once_at_each_dpi(self):
        probe = TaskbarLayoutProbe()
        probe._handle = 123
        probe._rects = ((0.25, 0.0, 0.5, 1.0),)
        probe._received = time.monotonic()
        self.assertEqual(probe.rectangles(123, (0, 912, 1536, 960)),
                         [(384, 912, 768, 960)])
        self.assertIsNone(probe.rectangles(123, (0, 1824, 3072, 1920)))
        # 新尺寸必须先有新的成功扫描，才可以重新映射坐标。
        self.feed_result(probe, {'ok': True, 'handle': 123,
                                 'rects': [[0.25, 0.0, 0.5, 1.0]]})
        self.assertEqual(probe.rectangles(123, (0, 1824, 3072, 1920)),
                         [(768, 1824, 1536, 1920)])
        self.assertIsNone(probe.rectangles(456, (0, 912, 1536, 960)))
        probe._received -= 5
        self.assertIsNone(probe.rectangles(123, (0, 912, 1536, 960)))
        probe.stop()

    @staticmethod
    def feed_result(probe, result):
        data = json.dumps(result).encode() + b'\n'
        with patch.object(probe._process, 'readAllStandardOutput', return_value=data):
            probe._read_output()

    def test_start_menu_keeps_last_layout_while_probe_reports_empty_tree(self):
        probe = TaskbarLayoutProbe()
        probe._handle = 123
        taskbar = (0, 0, 1000, 48)
        with patch('app.utils.taskbar_layout.time.monotonic', return_value=10.0):
            self.feed_result(probe, {'ok': True, 'handle': 123,
                                     'rects': [[0, 0, 0.4, 1], [0.8, 0, 1, 1]]})
            initial = probe.rectangles(123, taskbar)
        # 开始菜单保持打开超过原先的四秒快照有效期，检测进程持续响应。
        for now in range(11, 31):
            with patch('app.utils.taskbar_layout.time.monotonic', return_value=float(now)):
                self.feed_result(probe, {'ok': False, 'handle': 123, 'rects': []})
                self.assertEqual(probe.rectangles(123, taskbar), initial)
        # 菜单关闭后使用新布局，若图标真的占满空档仍应隐藏监控。
        self.feed_result(probe, {'ok': True, 'handle': 123, 'rects': [[0, 0, 1, 1]]})
        self.assertIsNone(free_taskbar_position(
            taskbar, probe.rectangles(123, taskbar), 164, 44, 4))
        probe.stop()

    def test_unreadable_layout_never_reuses_cache_after_geometry_change(self):
        probe = TaskbarLayoutProbe()
        probe._handle = 123
        self.feed_result(probe, {'ok': True, 'handle': 123, 'rects': [[0, 0, 0.4, 1]]})
        self.assertIsNotNone(probe.rectangles(123, (0, 0, 1000, 48)))
        self.feed_result(probe, {'ok': False})
        self.assertIsNone(probe.rectangles(123, (0, 0, 2000, 96)))
        self.feed_result(probe, {'ok': False})
        self.assertIsNone(probe.rectangles(123, (0, 0, 2000, 96)))
        probe.stop()

    def test_stalled_helper_is_killed_while_event_loop_keeps_running(self):
        probe = TaskbarLayoutProbe()
        loop = QEventLoop()
        beats = []
        heartbeat = QTimer()
        heartbeat.setInterval(20)
        heartbeat.timeout.connect(lambda: beats.append(time.monotonic()))
        heartbeat.start()
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        probe._process.finished.connect(loop.quit)
        with patch('app.utils.taskbar_layout._PROBE_SCRIPT', 'Start-Sleep -Seconds 30'):
            probe.start(123)
        deadline.start(6500)
        try:
            loop.exec()
            self.assertEqual(probe._process.state(), QProcess.ProcessState.NotRunning)
            self.assertIsNone(probe.rectangles(123, (0, 0, 1000, 48)))
            self.assertGreater(len(beats), 100)
            self.assertLess(max(b - a for a, b in zip(beats, beats[1:])), 0.5)
        finally:
            heartbeat.stop()
            deadline.stop()
            probe.stop()


if __name__ == '__main__':
    unittest.main()
