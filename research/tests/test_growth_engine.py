import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from growth_engine import simulate


class TestGrowthEngine(unittest.TestCase):
    def setUp(self):
        # a modest positive edge pool: +0.30R average
        rng = np.random.default_rng(3)
        self.pool = np.where(rng.random(4000) < 0.55, 1.5, -1.0)

    def test_fields(self):
        s = simulate(self.pool, 100.0, 1000.0, 100.0, 0.0075, 1.0, paths=2000)
        for k in ("P_reach", "P_ruin", "median_years", "median_max_dd"):
            self.assertIn(k, s)
        self.assertLessEqual(s["P_reach"] + s["P_ruin"], 1.0 + 1e-9)

    def test_trade_scaling_is_a_calendar_lever(self):
        # same edge, same odds, but scaling trades should not change P(reach) much
        # while it should shorten the median time.
        base = simulate(self.pool, 100.0, 5000.0, 50.0, 0.01, 0.5, paths=4000,
                        scale_trades=False)
        fast = simulate(self.pool, 100.0, 5000.0, 50.0, 0.01, 0.5, paths=4000,
                        scale_trades=True)
        self.assertAlmostEqual(base["P_reach"], fast["P_reach"], delta=0.08)
        self.assertLess(fast["median_years"], base["median_years"])

    def test_no_edge_ruins(self):
        rng = np.random.default_rng(5)
        pool = np.where(rng.random(4000) < 0.5, 1.0, -1.0)  # ~zero edge
        s = simulate(pool, 100.0, 100000.0, 200.0, 0.02, 0.5, paths=3000,
                     scale_trades=True)
        self.assertGreater(s["P_ruin"], 0.5)

    def test_min_lot_floor_raises_ruin(self):
        # a large min-lot risk relative to a tiny start should be much more fragile
        low = simulate(self.pool, 12.0, 5000.0, 300.0, 0.0075, 0.19, paths=4000,
                       scale_trades=True)
        high = simulate(self.pool, 12.0, 5000.0, 300.0, 0.0075, 1.86, paths=4000,
                        scale_trades=True)
        self.assertGreater(high["P_ruin"], low["P_ruin"])


if __name__ == "__main__":
    unittest.main()
