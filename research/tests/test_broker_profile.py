import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from broker_profile import BrokerProfile


STANDARD = """
symbol=XAUUSD
contract_size=100
min_lot=0.01
lot_step=0.01
max_lot=100
tick_size=0.01
tick_value=1.0
point=0.01
digits=2
spread_points=30
commission_per_lot=7.0
account_equity=10000
account_currency=USD
"""

MICRO = """
symbol=XAUUSD.m
contract_size=10
min_lot=0.01
tick_size=0.01
tick_value=0.10
point=0.01
spread_points=35
account_equity=500
"""


class TestParse(unittest.TestCase):
    def test_parse_standard(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        self.assertEqual(bp.symbol, "XAUUSD")
        self.assertEqual(bp.contract_size, 100)
        self.assertEqual(bp.commission_per_lot, 7.0)

    def test_parse_micro_keeps_defaults_for_missing(self):
        bp = BrokerProfile.from_mt5_kv(MICRO)
        self.assertEqual(bp.contract_size, 10)
        self.assertEqual(bp.digits, 2)          # default retained
        self.assertEqual(bp.min_lot, 0.01)

    def test_ignores_comments_and_unknown(self):
        bp = BrokerProfile.from_mt5_kv("# comment\nfoo=bar\ncontract_size=50")
        self.assertEqual(bp.contract_size, 50)


class TestDerived(unittest.TestCase):
    def test_point_value_per_lot(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        # tick_value 1.0 per tick, tick==point -> 1.0 per point per lot
        self.assertAlmostEqual(bp.point_value_per_lot, 1.0, places=9)

    def test_round_trip_cost(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        # spread 30 pts * 0.01 = 0.30 ; commission 7/100 = 0.07 -> 0.37
        self.assertAlmostEqual(bp.round_trip_cost_price, 0.37, places=9)

    def test_breakeven_win_standard(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        # (SL + s)/(TP+SL) = (1.0+0.37)/(0.5+1.0) = 0.9133..
        self.assertAlmostEqual(bp.breakeven_win(0.5, 1.0), 1.37 / 1.5, places=9)


class TestSizing(unittest.TestCase):
    def test_min_lot_risk_standard(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        # (stop 6 + cost 0.37) * contract 100 * min_lot 0.01 = 6.37
        self.assertAlmostEqual(bp.min_lot_risk(6.0), 6.37, places=6)

    def test_small_account_cannot_honor_risk_standard(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        bp.account_equity = 100.0
        # one min lot risks 6.37 = 6.37% of $100, exceeds 1%
        self.assertFalse(bp.can_trade(6.0, 1.0))

    def test_micro_account_can(self):
        bp = BrokerProfile.from_mt5_kv(MICRO)
        # (6 + 0.35) * 10 * 0.01 = 0.635 -> 0.127% of $500, fine at 1%
        self.assertTrue(bp.can_trade(6.0, 1.0))

    def test_lots_for_risk_respects_min(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        lots = bp.lots_for_risk(6.0, 0.0001)   # absurdly small risk
        self.assertEqual(lots, bp.min_lot)     # floored at the broker minimum

    def test_lots_for_risk_scales(self):
        bp = BrokerProfile.from_mt5_kv(STANDARD)
        a = bp.lots_for_risk(6.0, 1.0)
        b = bp.lots_for_risk(6.0, 2.0)
        # doubling risk doubles lots, up to independent rounding to the lot step
        self.assertAlmostEqual(b, 2 * a, delta=2 * bp.lot_step)


if __name__ == "__main__":
    unittest.main()
