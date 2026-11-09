import unittest
from types import SimpleNamespace

from app.ui.taskbar_monitor import TaskbarMonitor


class TaskbarMetricLayoutTests(unittest.TestCase):
    @staticmethod
    def monitor(metrics):
        monitor = TaskbarMonitor.__new__(TaskbarMonitor)
        monitor._settings = SimpleNamespace(taskbar_monitor_metrics=metrics)
        return monitor

    def test_selected_metrics_fill_the_first_percent_slot(self):
        monitor = self.monitor(("mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_columns(),
            [("mem", None), ("gpu", None)],
        )

    def test_selected_metrics_are_packed_row_major(self):
        monitor = self.monitor(("cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_columns(),
            [("cpu", "gpu"), ("mem", None)],
        )


if __name__ == "__main__":
    unittest.main()
