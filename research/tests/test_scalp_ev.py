import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import scalp_ev


class TestBreakEven(unittest.TestCase):
    def test_symmetric_with_no_spread(self):
        # TP=SL and no spread -> must win > 50%
        self.assertAlmostEqual(scalp_ev.breakeven_win(1.0, 1.0, 0.0), 0.5, places=9)

    def test_spread_raises_required_win(self):
        base = scalp_ev.breakeven_win(0.5, 1.0, 0.0)
        with_spread = scalp_ev.breakeven_win(0.5, 1.0, 0.2)
        self.assertGreater(with_spread, base)

    def test_tight_tp_wide_spread_is_impossible(self):
        # TP 0.2, SL 0.5, spread 0.3 -> break-even > 100%, i.e. unwinnable
        self.assertGreater(scalp_ev.breakeven_win(0.2, 0.5, 0.3), 1.0)

    def test_known_value(self):
        # p* = (SL + s) / (TP + SL) = (1.0 + 0.2) / (0.5 + 1.0) = 0.8
        self.assertAlmostEqual(scalp_ev.breakeven_win(0.5, 1.0, 0.2), 0.8, places=9)


class TestEdge(unittest.TestCase):
    def test_zero_edge_at_breakeven(self):
        pstar = scalp_ev.breakeven_win(0.5, 1.0, 0.2)
        self.assertAlmostEqual(scalp_ev.edge_per_trade(0.5, 1.0, 0.2, pstar), 0.0, places=12)

    def test_positive_above_breakeven(self):
        self.assertGreater(scalp_ev.edge_per_trade(0.5, 1.0, 0.2, 0.85), 0.0)

    def test_negative_below_breakeven(self):
        self.assertLess(scalp_ev.edge_per_trade(0.5, 1.0, 0.2, 0.75), 0.0)


class TestSimulate(unittest.TestCase):
    tiers = [(0, 0.01), (25, 0.02), (50, 0.03)]

    def test_edge_survives(self):
        s = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.85, 1.0, 50, 250, 2000)
        self.assertLess(s["P_ruin"], 0.05)
        self.assertGreater(s["final_median"], 10.0)

    def test_no_edge_ruins(self):
        s = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.75, 1.0, 50, 250, 2000)
        self.assertGreater(s["P_ruin"], 0.95)

    def test_deterministic_seed(self):
        a = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.85, 1.0, 50, 250, 500, seed=1)
        b = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.85, 1.0, 50, 250, 500, seed=1)
        self.assertEqual(a, b)

    def test_target_reported(self):
        s = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.85, 1.0, 50, 250, 2000,
                              target=100.0)
        self.assertIn("P_reach", s)
        self.assertIn("median_trades_to_target", s)
        self.assertGreaterEqual(s["P_reach"], 0.0)
        self.assertLessEqual(s["P_reach"], 1.0)

    def test_target_not_given_still_works(self):
        s = scalp_ev.simulate(10.0, self.tiers, 0.5, 1.0, 0.2, 0.85, 1.0, 50, 250, 2000)
        self.assertNotIn("P_reach", s)


if __name__ == "__main__":
    unittest.main()
