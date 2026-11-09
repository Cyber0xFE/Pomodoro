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

    def test_selected_metrics_stay_contiguous_on_the_top_row(self):
        monitor = self.monitor(("cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_columns(),
            [("cpu", None), ("mem", None), ("gpu", None)],
        )

    def test_down_only_network_uses_the_bottom_row_for_metrics(self):
        monitor = self.monitor(("mem", "gpu", "down"))
        self.assertEqual(
            monitor._visible_metric_columns(),
            [(None, "mem"), (None, "gpu")],
        )


if __name__ == "__main__":
    unittest.main()
