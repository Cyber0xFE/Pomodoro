import unittest
from types import SimpleNamespace

from app.ui.taskbar_monitor import TaskbarMonitor


class TaskbarMetricLayoutTests(unittest.TestCase):
    @staticmethod
    def monitor(metrics):
        monitor = TaskbarMonitor.__new__(TaskbarMonitor)
        monitor._settings = SimpleNamespace(taskbar_monitor_metrics=metrics)
        return monitor

    def test_metrics_share_one_row_when_it_fits_without_network(self):
        monitor = self.monitor(("mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["mem", "gpu"], []),
        )

    def test_overflow_moves_to_empty_row_and_keeps_rows_compact(self):
        monitor = self.monitor(("down", "cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["mem", "gpu"], ["cpu"]),
        )

    def test_three_metrics_without_network_split_evenly(self):
        monitor = self.monitor(("cpu", "mem", "gpu"))
        self.assertEqual(
            monitor._visible_metric_rows(),
            (["cpu", "mem"], ["gpu"]),
        )


if __name__ == "__main__":
    unittest.main()
