import unittest

from app.core.monitor import (
    MonitorSnapshot,
    _WindowsPerformanceCounters,
    _disk_utilization,
    _gpu_utilization,
)


class MonitorMetricReducerTests(unittest.TestCase):
    def test_gpu_uses_busiest_engine_across_physical_adapters(self):
        samples = [
            ("pid_123_luid_0x1_phys_0_eng_3D_0", 64.0),
            ("pid_456_luid_0x1_phys_0_eng_3D_0", 36.0),
            ("luid_0x1_phys_0_eng_Copy_0", 41.0),
            ("luid_0x2_phys_1_eng_3D_0", 55.0),
            # Separate processes sharing the 3D engine aggregate to 100%.
            ("pid_789_luid_0x1_phys_0_eng_3D_0", 14.0),
        ]
        self.assertEqual(_gpu_utilization(samples), 100.0)

    def test_gpu_clamps_driver_values(self):
        self.assertEqual(_gpu_utilization([("luid_0x1_phys_0_eng_3D_0", 140)]), 100.0)
        self.assertIsNone(_gpu_utilization([]))

    def test_gpu_groups_multi_part_luid_instances(self):
        samples = [
            ("pid_1_luid_0x00000000_0x000100B9_phys_0_eng_0_engtype_3D", 42.0),
            ("pid_2_luid_0x00000000_0x000100B9_phys_0_eng_0_engtype_3D", 37.0),
        ]
        self.assertEqual(_gpu_utilization(samples), 79.0)

    def test_disk_uses_busiest_physical_disk_and_ignores_total(self):
        samples = [("0 C:", 91.0), ("1 D:", 20.0), ("_Total", 50.0)]
        self.assertEqual(_disk_utilization(samples), 80.0)

    def test_disk_falls_back_to_total_when_no_physical_instance(self):
        self.assertEqual(_disk_utilization([("_Total", 73.0)]), 27.0)
        self.assertIsNone(_disk_utilization([]))

    def test_snapshot_keeps_unavailable_metrics_distinct_from_zero(self):
        snapshot = MonitorSnapshot()
        self.assertIsNone(snapshot.gpu_percent)
        self.assertIsNone(snapshot.disk_percent)

    def test_backend_is_safe_when_pdh_is_unavailable(self):
        backend = _WindowsPerformanceCounters()
        backend.start()
        sample = backend.sample()
        if backend.available:
            for value in sample:
                self.assertTrue(value is None or 0.0 <= value <= 100.0)
        else:
            self.assertEqual(sample, (None, None))
        backend.stop()
        self.assertEqual(backend.sample(), (None, None))


if __name__ == "__main__":
    unittest.main()
