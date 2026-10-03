//+------------------------------------------------------------------+
//|                                            XauBreakoutEA.mq5     |
//|                                                                  |
//|  A transparent XAUUSD breakout EA.                               |
//|                                                                  |
//|  Structure (deliberately layered, so each part is testable):     |
//|    1. Signal   : Donchian breakout of the prior N completed bars  |
//|    2. Filter   : confirmation (close beyond level, session, news)|
//|    3. Risk     : ATR-based stop, percent-risk sizing, hard caps  |
//|    4. Execute  : market entry on breakout, SL/TP, trailing stop   |
//|                                                                  |
//|  Design rules this EA follows on purpose:                        |
//|    - No grid. No martingale. Every position has a hard stop.     |
//|    - Size is derived from the *actual* stop distance.            |
//|    - Trading only on completed bars (no intra-bar repaint).      |
//|    - Nothing hard-coded to a broker/symbol suffix.               |
//+------------------------------------------------------------------+
#property copyright   "OpenHands"
#property version     "1.00"
#property description "XAUUSD breakout EA - hard stops, percent-risk sizing, no grid."

#include <Trade/Trade.mqh>
#include <Trade/SymbolInfo.mqh>
#include <RiskManager.mqh>
#include <NewsGuard.mqh>

//--- inputs ---------------------------------------------------------
input group "=== Signal ==="
input int    InpLookbackBars     = 60;      // Breakout lookback (bars)
input int    InpAtrPeriod        = 14;      // ATR period
input bool   InpRequireCloseOut  = true;    // Require bar close beyond level

input group "=== Risk ==="
input double InpRiskPercent      = 0.75;    // Risk per trade (% of equity)
input double InpStopAtrMult      = 1.50;    // Stop distance (x ATR)
input double InpRewardRisk       = 2.00;    // Take profit (R multiple)
input double InpMaxTotalRiskPct  = 3.00;    // Max total open risk (% equity)
input double InpMaxDailyLossPct  = 2.00;    // Max daily loss (% equity), 0=off
input int    InpMaxPositions     = 1;       // Max simultaneous positions

input group "=== Trade management ==="
input bool   InpUseTrailing      = true;    // Enable ATR trailing stop
input double InpTrailAtrMult     = 2.00;    // Trailing distance (x ATR)
input double InpTrailStartR      = 1.00;    // Start trailing after this R

input group "=== Filters ==="
input bool   InpUseSession       = true;    // Restrict to London/NY hours
input int    InpSessionStartHour = 7;       // Session start (server hour)
input int    InpSessionEndHour   = 20;      // Session end (server hour)
input int    InpFridayStopHour   = 20;      // Stop new trades Fri after this hour (25=off)
input double InpMaxSpreadPoints  = 60;      // Max spread in points (0=off)

input group "=== News ==="
input bool   InpUseNewsFilter    = true;    // Block around high-impact news
input int    InpNewsBeforeMin    = 15;      // Minutes before event
input int    InpNewsAfterMin     = 15;      // Minutes after event

input group "=== Execution ==="
input ulong  InpMagic            = 20261003; // Magic number
input int    InpSlippagePoints   = 30;      // Slippage (points)
input int    InpRandomSpread     = 0;       // Randomise entry by 0..N points (0=off)

//--- globals --------------------------------------------------------
CTrade         trade;
CRiskManager   risk;
CNewsGuard     news;
CSymbolInfo    sym;
int            h_atr = INVALID_HANDLE;
datetime       last_bar_time = 0;

//--- trade-event state (see OnTradeTransaction) ---------------------
ulong          g_pending_request = 0;   // request id we are still waiting to confirm

//+------------------------------------------------------------------+
int OnInit(void)
{
   if(!sym.Name(_Symbol))
      return(INIT_FAILED);
   sym.RefreshRates();

   if(!risk.Init(_Symbol))
   {
      Print("RiskManager init failed");
      return(INIT_FAILED);
   }
   if(!risk.Validate())
   {
      Print("XauBreakoutEA refused to start: symbol contract failed validation");
      return(INIT_FAILED);
   }
   news.Init(_Symbol, InpNewsBeforeMin, InpNewsAfterMin);

   h_atr = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   if(h_atr == INVALID_HANDLE)
   {
      Print("Failed to create ATR handle");
      return(INIT_FAILED);
   }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetMarginMode();

   MathSrand((uint)TimeLocal() + (uint)InpMagic);   // seed once, not per tick

   PrintFormat("XauBreakoutEA init on %s, digits=%d, point=%.5f, tickvalue=%.5f",
               _Symbol, sym.Digits(), sym.Point(), sym.TickValue());
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(h_atr != INVALID_HANDLE)
      IndicatorRelease(h_atr);
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool NewBar(void)
{
   datetime t = (datetime)iTime(_Symbol, PERIOD_CURRENT, 0);
   if(t == last_bar_time)
      return(false);
   last_bar_time = t;
   return(true);
}

double AtrValue(void)
{
   double buf[];
   if(CopyBuffer(h_atr, 0, 0, 2, buf) < 2)
      return(0.0);
   return(buf[1]);          // last completed bar's ATR
}

bool SessionOk(void)
{
   if(!InpUseSession)
      return(true);
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   if(t.day_of_week == 0 || t.day_of_week == 6)
      return(false);
   if(t.day_of_week == 5 && InpFridayStopHour <= 23 && t.hour >= InpFridayStopHour)
      return(false);
   return(t.hour >= InpSessionStartHour && t.hour < InpSessionEndHour);
}

bool SpreadOk(void)
{
   if(InpMaxSpreadPoints <= 0.0)
      return(true);
   sym.RefreshRates();
   double spread_pts = (sym.Ask() - sym.Bid()) / sym.Point();
   return(spread_pts <= InpMaxSpreadPoints);
}

//+------------------------------------------------------------------+
//| Trailing stop: move SL to lock in profit once trade is in R      |
//+------------------------------------------------------------------+
void ManageTrailing(const double atr)
{
   if(!InpUseTrailing || atr <= 0.0)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;

      double open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl     = PositionGetDouble(POSITION_STOPLOSS);
      double tp     = PositionGetDouble(POSITION_TP);
      long   type   = PositionGetInteger(POSITION_TYPE);
      double point  = sym.Point();
      double trail  = InpTrailAtrMult * atr;

      if(type == POSITION_TYPE_BUY)
      {
         double profit_dist = sym.Bid() - open;
         if(profit_dist < InpTrailStartR * InpStopAtrMult * atr)
            continue;
         double new_sl = sym.Bid() - trail;
         if(new_sl > sl + point && new_sl < sym.Bid())
            trade.PositionModify(ticket, NormalizeDouble(new_sl, sym.Digits()), tp);
      }
      else if(type == POSITION_TYPE_SELL)
      {
         double profit_dist = open - sym.Ask();
         if(profit_dist < InpTrailStartR * InpStopAtrMult * atr)
            continue;
         double new_sl = sym.Ask() + trail;
         if((sl == 0.0 || new_sl < sl - point) && new_sl > sym.Ask())
            trade.PositionModify(ticket, NormalizeDouble(new_sl, sym.Digits()), tp);
      }
   }
}

//+------------------------------------------------------------------+
//| Signal: Donchian breakout of prior N bars, buffered by ATR       |
//+------------------------------------------------------------------+
void OnTick(void)
{
   double atr = AtrValue();
   if(atr <= 0.0)
      return;

   ManageTrailing(atr);          // responsive: runs on every tick

   if(!NewBar())                 // signal logic only on completed bars
      return;

   //--- account guards
   if(risk.DailyLossBreached((long)InpMagic, InpMaxDailyLossPct))
      return;
   if(risk.CountPositions((long)InpMagic) >= InpMaxPositions)
      return;
   if(!SessionOk() || !SpreadOk())
      return;
   if(InpUseNewsFilter && news.IsBlocked())
      return;

   //--- Donchian channel from bars *before* the breakout bar (shift 2),
   //    so the channel never includes the bar whose close we test.
   int    highest = iHighest(_Symbol, PERIOD_CURRENT, MODE_HIGH, InpLookbackBars, 2);
   int    lowest  = iLowest (_Symbol, PERIOD_CURRENT, MODE_LOW,  InpLookbackBars, 2);
   if(highest < 0 || lowest < 0)
      return;

   double hi = iHigh(_Symbol, PERIOD_CURRENT, highest);
   double lo = iLow (_Symbol, PERIOD_CURRENT, lowest);
   double close1 = iClose(_Symbol, PERIOD_CURRENT, 1);

   bool long_ok  = InpRequireCloseOut ? (close1 > hi)
                                      : (iHigh(_Symbol, PERIOD_CURRENT, 1) > hi);
   bool short_ok = InpRequireCloseOut ? (close1 < lo)
                                      : (iLow(_Symbol, PERIOD_CURRENT, 1) < lo);

   //--- risk budget check (only if a cap is set)
   double use_risk = InpRiskPercent;
   if(InpMaxTotalRiskPct > 0.0)
   {
      double budget_pct = risk.RemainingRiskBudgetPercent((long)InpMagic, InpMaxTotalRiskPct);
      use_risk = MathMin(InpRiskPercent, budget_pct);
   }
   if(use_risk <= 0.0)
      return;

   double stop_pts = (InpStopAtrMult * atr) / sym.Point();
   double lots     = risk.LotsForRisk(use_risk, stop_pts);
   if(lots <= 0.0)
      return;

   double buffer_pts = (InpRandomSpread > 0)
                       ? (double)(MathRand() % (InpRandomSpread + 1))
                       : 0.0;

   if(long_ok)
   {
      double entry = NormalizeDouble(sym.Ask() + buffer_pts * sym.Point(), sym.Digits());
      double sl    = NormalizeDouble(entry - InpStopAtrMult * atr, sym.Digits());
      double tp    = NormalizeDouble(entry + InpRewardRisk * InpStopAtrMult * atr, sym.Digits());
      if(trade.Buy(lots, _Symbol, 0.0, sl, tp, "XauBreakout"))
         g_pending_request = trade.Result().request_id;
      else
         Print("XauBreakoutEA entry rejected: ", trade.ResultRetcodeDescription());
   }
   else if(short_ok)
   {
      double entry = NormalizeDouble(sym.Bid() - buffer_pts * sym.Point(), sym.Digits());
      double sl    = NormalizeDouble(entry + InpStopAtrMult * atr, sym.Digits());
      double tp    = NormalizeDouble(entry - InpRewardRisk * InpStopAtrMult * atr, sym.Digits());
      if(trade.Sell(lots, _Symbol, 0.0, sl, tp, "XauBreakout"))
         g_pending_request = trade.Result().request_id;
      else
         Print("XauBreakoutEA entry rejected: ", trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| Trade transactions                                               |
//|                                                                  |
//| The terminal may report a request's stages (accepted, order      |
//| placed, deal executed, position opened) in any order, so we do   |
//| not assume a sequence. We only:                                  |
//|   - confirm that the position we asked for actually appeared      |
//|   - record server rejections so they are visible, not silent      |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   //--- surface a rejection for the request we were waiting on
   if(trans.type == TRADE_TRANSACTION_REQUEST && result.request_id == g_pending_request)
   {
      if(result.retcode != TRADE_RETCODE_DONE && result.retcode != TRADE_RETCODE_PLACED)
      {
         PrintFormat("XauBreakoutEA request %I64u rejected: %d (%s)",
                     result.request_id, result.retcode, result.comment);
         g_pending_request = 0;
      }
   }

   //--- confirm the entry: a deal for our symbol/order actually executed
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD && trans.symbol == _Symbol)
   {
      if(trans.order == g_pending_request && g_pending_request != 0)
      {
         PrintFormat("XauBreakoutEA entry confirmed: deal %I64u, price %.2f, vol %.2f",
                     trans.deal, trans.price, trans.volume);
         g_pending_request = 0;
      }
   }
}

//+------------------------------------------------------------------+
//| Custom optimisation criterion: prefer return, punish drawdown    |
//+------------------------------------------------------------------+
double OnTester(void)
{
   double profit = TesterStatistics(STAT_PROFIT);
   double dd_pct = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
   double trades = TesterStatistics(STAT_TRADES);
   double pf     = TesterStatistics(STAT_PROFIT_FACTOR);

   if(trades < 30 || dd_pct <= 0.0)
      return(0.0);
   if(pf < 1.1)
      return(0.0);
   return(profit / dd_pct);
}
//+------------------------------------------------------------------+
