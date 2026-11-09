import unittest
from types import SimpleNamespace

from app.ui.taskbar_monitor import TaskbarMonitor


class TaskbarMetricLayoutTests(unittest.TestCase):
    @staticmethod
    def monitor(metrics):
        monitor = TaskbarMonitor.__new__(TaskbarMonitor)
        monitor._settings = SimpleNamespace(taskbar_monitor_metrics=metrics)
        return monitor

    def test_two_metrics_prefer_vertical_positions(self):
        monitor = self.monitor(("mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["mem"], ["gpu"]),
        )

    def test_metrics_balance_around_a_selected_network_row(self):
        monitor = self.monitor(("down", "cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["cpu", "gpu"], ["mem"]),
        )

    def test_down_network_and_one_metric_use_separate_rows(self):
        monitor = self.monitor(("down", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["gpu"], []),
        )

    def test_three_metrics_without_network_fill_both_rows_first(self):
        monitor = self.monitor(("cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["cpu", "gpu"], ["mem"]),
        )


if __name__ == "__main__":
    unittest.main()
