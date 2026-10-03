# AGENTS.md

## Project
MQL5 Expert Advisor development. Current target: `Experts/XauBreakoutEA/` — a
transparent XAUUSD breakout EA, structured after the *approach* (not code) of
"Gold Reaper" on the MQL5 Market.

## Layout
- `Experts/XauBreakoutEA/XauBreakoutEA.mq5` — EA entry point (signal + orchestration)
- `Include/RiskManager.mqh` — position sizing, exposure/daily-loss guards
- `Include/NewsGuard.mqh` — economic-calendar blackout filter
- `research/` — Python harness that validates the strategy idea on real gold data
  (COMEX futures `GC=F` as XAUUSD proxy). See `research/FINDINGS.md`.

## Validated findings (research/FINDINGS.md)
The breakout + ATR-stop + percent-risk idea was validated out-of-sample:
- Walk-forward daily: 6/6 folds positive OOS, mean OOS PF 1.79, IS->OOS gap 3.4 pts
- Survives 3x costs (PF 1.53 -> 1.37); bootstrap MC prob(loss) 0.2%
- `stop_atr` is the sensitive parameter; optimum sits at the aggressive edge of
  the tested range, so prefer the wider (1.5x ATR) setting.
Caveat: futures proxy, bar-level fidelity, no news filter in the harness.

## Deployment target: Deriv MT5
The user trades on **Deriv MT5**. See `DERIV_SETUP.md` for the full guide. Key points:
- Use the **Gold** or **Financial** account (real XAUUSD). The **Standard/Derived**
  account has only synthetic indices (Volatility, Boom/Crash) - NOT gold.
- `CRiskManager::Validate()` runs at init: it aborts if contract size, tick value,
  or bid are unusable, and warns on non-100-oz contracts. Sizing is contract-size
  agnostic (uses tick value), so micro contracts stay correct.
- **Minimum-lot trap**: on small accounts the risk-based size can fall below the
  broker minimum and get clamped up, over-risking. Verify on demo.
- Deriv server time offset is disputed in public sources - measure it, don't assume.
- Deriv charges no commission; harness shows the edge survives a 0.60 spread.

## How it maps into a real MT5 install
MetaEditor resolves `<...>` includes against the terminal's `MQL5/` root, so:
- copy `Include/*.mqh`  -> `MQL5/Include/`
- copy `Experts/XauBreakoutEA/` -> `MQL5/Experts/XauBreakoutEA/`
Then compile in MetaEditor (F7). `MQL5/Experts` is what the Navigator shows.

## Design rules (do not violate when extending)
- No grid, no martingale. Every position carries a hard stop loss.
- Position size is derived from the *actual* stop distance (see `LotsForRisk`).
- Signal logic runs only on completed bars (`NewBar()`); trailing runs per tick.
- Never hard-code a broker/symbol suffix; use `_Symbol` and `CSymbolInfo`.
- Marketplace rules: no DLLs. External HTTP requires an allowed URL. The news
  filter uses the built-in calendar to stay compliant.

## Testing workflow (the part that matters)
1. Compile in MetaEditor.
2. Strategy Tester: XAUUSD, **every tick based on real ticks**, real spread +
   commission + swap. "Open prices only" flatters results — don't trust it.
3. Optimize on a train window; validate on an unseen out-of-sample window.
4. Forward-test on a demo account for weeks before any live capital.
5. Perturb inputs ~10%; if the equity curve collapses, it is overfit.

## Environment note
Development happens on Linux; there is no MetaEditor here, so MQL5 cannot be
compiled or run locally. Changes are validated by inspection + balance checks.
