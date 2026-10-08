#!/usr/bin/env python3
"""
Broker profile: everything the EV needs about a broker, detected not assumed.

The EV must not be built for one broker. Position size, cost and break-even all
depend on the symbol's contract spec, and those specs differ by broker and even
by account type (standard / micro / cent). So instead of hard-coding Deriv (or
anyone), we detect the spec once and derive everything from it.

In MetaTrader 5 every field below is available from SymbolInfo* calls, so the EA
can print them at init and the research side can consume them. Nothing here is
broker-specific - the same code works for a 100 oz standard contract, a 10 oz
micro, or a 1 oz cent account.

MT5 source of each field:
    contract_size     SymbolInfoDouble(SYMBOL_TRADE_CONTRACT_SIZE)
    min_lot           SymbolInfoDouble(SYMBOL_VOLUME_MIN)
    lot_step          SymbolInfoDouble(SYMBOL_VOLUME_STEP)
    max_lot           SymbolInfoDouble(SYMBOL_VOLUME_MAX)
    tick_size         SymbolInfoDouble(SYMBOL_TRADE_TICK_SIZE)
    tick_value        SymbolInfoDouble(SYMBOL_TRADE_TICK_VALUE)
    point             SymbolInfoDouble(SYMBOL_POINT)
    digits            SymbolInfoInteger(SYMBOL_DIGITS)
    spread_points     (SymbolInfoDouble(SYMBOL_ASK) - SYMBOL_BID) / point
    commission/lot    from closed-deal history (DEAL_COMMISSION), or user input
    stops_level       SymbolInfoInteger(SYMBOL_TRADE_STOPS_LEVEL)

Usage:
    from broker_profile import BrokerProfile
    bp = BrokerProfile.from_mt5_kv(open("spec.txt").read())
    print(bp.summary())
    print(bp.breakeven_win(tp=0.5, sl=1.0))
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class BrokerProfile:
    symbol: str = "XAUUSD"
    contract_size: float = 100.0     # units (oz) per 1.0 lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0
    tick_size: float = 0.01
    tick_value: float = 1.0          # account ccy per tick per 1.0 lot
    point: float = 0.01
    digits: int = 2
    spread_points: float = 30.0      # current spread, in points
    commission_per_lot: float = 0.0  # round-trip, account ccy per 1.0 lot
    stops_level_points: float = 0.0
    account_equity: float = 10000.0
    account_currency: str = "USD"

    # ------------------------------------------------------------------
    # derived quantities - all from the detected spec, nothing assumed
    # ------------------------------------------------------------------
    @property
    def point_value_per_lot(self) -> float:
        """Account currency value of a 1-point move for 1.0 lot."""
        if self.tick_size <= 0:
            return 0.0
        return self.tick_value * (self.point / self.tick_size)

    @property
    def spread_price(self) -> float:
        """Spread expressed in price units."""
        return self.spread_points * self.point

    @property
    def commission_price(self) -> float:
        """Round-trip commission expressed in price units per unit."""
        if self.contract_size <= 0:
            return 0.0
        return self.commission_per_lot / self.contract_size

    @property
    def round_trip_cost_price(self) -> float:
        """Total cost per unit (spread + commission) in price units."""
        return self.spread_price + self.commission_price

    def min_lot_risk(self, stop_price: float) -> float:
        """Account currency risked by the minimum lot at a given stop distance."""
        return (stop_price + self.round_trip_cost_price) * self.contract_size * self.min_lot

    def can_trade(self, stop_price: float, risk_pct: float) -> bool:
        """Can the account take ONE minimum lot without exceeding risk_pct?"""
        if self.account_equity <= 0:
            return False
        return self.min_lot_risk(stop_price) <= self.account_equity * risk_pct / 100.0

    def lots_for_risk(self, stop_price: float, risk_pct: float) -> float:
        """Lots so a stop at stop_price risks risk_pct of equity, at/above min lot."""
        per_lot = (stop_price + self.round_trip_cost_price) * self.contract_size
        if per_lot <= 0:
            return 0.0
        raw = (self.account_equity * risk_pct / 100.0) / per_lot
        if self.lot_step > 0:
            raw = round(raw / self.lot_step) * self.lot_step
        return max(self.min_lot, min(self.max_lot, raw))

    def breakeven_win(self, tp: float, sl: float) -> float:
        """Win rate required to break even after the DETECTED round-trip cost."""
        s = self.round_trip_cost_price
        den = tp + sl
        return (sl + s) / den if den > 0 else float("nan")

    # ------------------------------------------------------------------
    # detection
    # ------------------------------------------------------------------
    @classmethod
    def from_mt5_kv(cls, text: str) -> "BrokerProfile":
        """Parse the key=value block an MT5 EA can Print() at init.

        Unknown keys are ignored; missing keys keep their defaults. Numbers are
        parsed leniently so a broker's locale formatting does not break it.
        """
        fields = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip().lower(), v.strip().strip('"')
            if k in {f for f in cls.__dataclass_fields__}:
                if k == "symbol" or k == "account_currency":
                    fields[k] = v
                else:
                    try:
                        fields[k] = float(v) if "." in v or "e" in v.lower() else int(v)
                    except ValueError:
                        continue
        return cls(**fields)

    def summary(self) -> str:
        return (
            f"broker profile: {self.symbol}\n"
            f"  contract        : {self.contract_size} units/lot\n"
            f"  lot             : min {self.min_lot}, step {self.lot_step}, max {self.max_lot}\n"
            f"  point/tick      : {self.point} / {self.tick_size}, digits {self.digits}\n"
            f"  tick value      : {self.tick_value} {self.account_currency} per tick per lot\n"
            f"  point value/lot : {self.point_value_per_lot:.5f} {self.account_currency}\n"
            f"  spread          : {self.spread_points} pts = {self.spread_price:.4f} price\n"
            f"  commission      : {self.commission_per_lot} {self.account_currency}/lot "
            f"= {self.commission_price:.4f} price\n"
            f"  round-trip cost : {self.round_trip_cost_price:.4f} price\n"
            f"  equity          : {self.account_equity:,.2f} {self.account_currency}"
        )


if __name__ == "__main__":
    # a micro-account example, to show nothing is hard-coded to a 100 oz contract
    demo = """
    # detected from SymbolInfo* at init
    symbol=XAUUSD.m
    contract_size=10
    min_lot=0.01
    lot_step=0.01
    max_lot=50
    tick_size=0.01
    tick_value=0.10
    point=0.01
    digits=2
    spread_points=35
    commission_per_lot=0.14
    account_equity=500
    account_currency=USD
    """
    bp = BrokerProfile.from_mt5_kv(demo)
    print(bp.summary())
    print(f"\nbreakeven win (TP 0.5 / SL 1.0): {bp.breakeven_win(0.5, 1.0)*100:.1f}%")
    print(f"min-lot risk at 1.5xATR($6):     ${bp.min_lot_risk(6.0):.2f}")
    print(f"can trade at 1% risk?            {bp.can_trade(6.0, 1.0)}")
