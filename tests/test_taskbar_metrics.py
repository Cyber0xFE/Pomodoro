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
        self.assertEqual(monitor._visible_metric_columns(), [("gpu", "mem")])

    def test_metric_family_order_is_stable_when_slots_are_missing(self):
        monitor = self.monitor(("cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_columns(),
            [("cpu", "mem"), ("gpu", None)],
        )


if __name__ == "__main__":
    unittest.main()
