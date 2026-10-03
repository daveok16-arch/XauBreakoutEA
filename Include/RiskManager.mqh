//+------------------------------------------------------------------+
//|                                                 RiskManager.mqh  |
//|   Position sizing + account-level risk guards.                    |
//|   Deliberately independent of any signal so it can be reused.     |
//+------------------------------------------------------------------+

#include <Trade/SymbolInfo.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/OrderInfo.mqh>

//+------------------------------------------------------------------+
//| RiskManager                                                       |
//|                                                                   |
//| Sizing model (mirrors the "max allowed drawdown" idea, but from   |
//| first principles rather than a hard-coded historical DD):         |
//|                                                                   |
//|   risk_money = equity * RiskPercent/100                           |
//|   lots       = risk_money / (stop_distance_points * point_value)  |
//|                                                                   |
//| We size from the *actual* stop distance, so a wider stop cannot   |
//| silently increase risk. This is the single most important rule.   |
//+------------------------------------------------------------------+
class CRiskManager
{
private:
   CSymbolInfo   m_sym;
   CPositionInfo m_pos;
   COrderInfo    m_ord;
   double        m_point;
   double        m_tick_value;    // value of one tick per 1.0 lot
   double        m_tick_size;
   int           m_digits;

public:
                     CRiskManager(void) { m_point=0; m_tick_value=0; m_tick_size=0; m_digits=0; }

   bool              Init(const string symbol)
   {
      if(!m_sym.Name(symbol))
         return(false);
      m_sym.RefreshRates();
      m_point      = m_sym.Point();
      m_digits     = m_sym.Digits();
      m_tick_size  = m_sym.TickSize();
      m_tick_value = m_sym.TickValue();
      return(m_point > 0.0 && m_tick_value > 0.0);
   }

   //--- money value of one point of movement for one lot
   double            PointValuePerLot(void) const
   {
      if(m_tick_size <= 0.0)
         return(0.0);
      return(m_tick_value * (m_point / m_tick_size));
   }

   //+---------------------------------------------------------------+
   //| Sanity-check the symbol contract before trusting it.            |
   //|                                                                 |
   //| Gold contracts differ by broker/account: contract size is        |
   //| usually 100 oz, but can be 10 (micro) or 1 (cent). The sizing    |
   //| math below is contract-size agnostic, but a tiny tick value can  |
   //| mean the symbol is untradeable for our purpose, and a decimal    |
   //| price (e.g. crypto) would make "points" meaningless. Reject      |
   //| anything that does not look like a metal/CFD price.              |
   //+---------------------------------------------------------------+
   bool              Validate(void)
   {
      double contract = m_sym.ContractSize();
      double bid      = m_sym.Bid();
      double tickval  = m_tick_value;
      double ptval    = PointValuePerLot();

      PrintFormat("XauBreakoutEA symbol check: %s contract=%.1f digits=%d point=%.5f "
                  "ticksize=%.5f tickvalue=%.5f pointvalue/lot=%.5f bid=%.2f",
                  m_sym.Name(), contract, m_digits, m_point, m_tick_size, tickval, ptval, bid);

      if(contract <= 0.0)
      {
         Print("XauBreakoutEA ERROR: contract size is zero/unknown for ", m_sym.Name());
         return(false);
      }
      if(ptval <= 0.0)
      {
         Print("XauBreakoutEA ERROR: point value per lot is zero - cannot size safely");
         return(false);
      }
      if(bid <= 0.0)
      {
         Print("XauBreakoutEA ERROR: no bid price yet; is the symbol in Market Watch?");
         return(false);
      }
      //--- a sane XAUUSD price sits in the hundreds-to-thousands of USD
      if(bid < 100.0 || bid > 100000.0)
      {
         PrintFormat("XauBreakoutEA WARNING: %s bid=%.2f does not look like gold. "
                     "Check you attached to the right symbol.", m_sym.Name(), bid);
      }
      if(contract != 100.0)
      {
         PrintFormat("XauBreakoutEA NOTE: contract size is %.1f (not the 100 oz standard). "
                     "Sizing uses tick value so it stays correct, but double-check the symbol.",
                     contract);
      }
      return(true);
   }

   //--- Normalise a raw lot to the broker's step/min/max for this symbol
   double            NormalizeLots(const double lots) const
   {
      double step = m_sym.LotsStep();
      double minl = m_sym.LotsMin();
      double maxl = m_sym.LotsMax();
      if(step <= 0.0)
         step = 0.01;
      double v = MathFloor(lots / step + 0.5) * step;
      if(v < minl) v = minl;
      if(v > maxl) v = maxl;
      return(NormalizeDouble(v, 2));
   }

   //+---------------------------------------------------------------+
   //| Core sizing: lots such that a stop at `stop_points` away loses  |
   //| at most `risk_percent` of current equity.                       |
   //+---------------------------------------------------------------+
   double            LotsForRisk(const double risk_percent, const double stop_points)
   {
      if(stop_points <= 0.0 || risk_percent <= 0.0)
         return(0.0);

      double equity      = AccountInfoDouble(ACCOUNT_EQUITY);
      double risk_money  = equity * risk_percent / 100.0;
      double loss_per_lot = stop_points * PointValuePerLot();

      if(loss_per_lot <= 0.0)
         return(0.0);

      return(NormalizeLots(risk_money / loss_per_lot));
   }

   //--- Total floating P/L of our own positions on this symbol
   double            FloatingPL(const long magic) 
   {
      double pl = 0.0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!m_pos.SelectByIndex(i))
            continue;
         if(m_pos.Symbol() != m_sym.Name())
            continue;
         if((long)m_pos.Magic() != magic)
            continue;
         pl += m_pos.Profit() + m_pos.Swap();
      }
      return(pl);
   }

   int               CountPositions(const long magic)
   {
      int n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!m_pos.SelectByIndex(i)) continue;
         if(m_pos.Symbol() != m_sym.Name()) continue;
         if((long)m_pos.Magic() != magic) continue;
         n++;
      }
      return(n);
   }

   int               CountPending(const long magic)
   {
      int n = 0;
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         if(!m_ord.SelectByIndex(i)) continue;
         if(m_ord.Symbol() != m_sym.Name()) continue;
         if((long)m_ord.Magic() != magic) continue;
         n++;
      }
      return(n);
   }

   //--- Daily loss guard: true if today's realised+floating loss exceeds limit
   bool              DailyLossBreached(const long magic, const double daily_limit_percent)
   {
      if(daily_limit_percent <= 0.0)
         return(false);

      MqlDateTime now;
      TimeToStruct(TimeCurrent(), now);
      now.hour = 0; now.min = 0; now.sec = 0;
      datetime day_start = StructToTime(now);

      HistorySelect(day_start, TimeCurrent());
      double realised = 0.0;
      int total = HistoryDealsTotal();
      for(int i = 0; i < total; i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket == 0) continue;
         if(HistoryDealGetString(ticket, DEAL_SYMBOL) != m_sym.Name()) continue;
         if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != magic) continue;
         realised += HistoryDealGetDouble(ticket, DEAL_PROFIT)
                   + HistoryDealGetDouble(ticket, DEAL_SWAP)
                   + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      }

      double floating   = FloatingPL(magic);
      double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
      double day_result = realised + floating;

      return(day_result < -(equity * daily_limit_percent / 100.0));
   }

   //--- Largest stop (in points) that keeps total open risk under a cap
   double            RemainingRiskBudgetPercent(const long magic, const double total_cap_percent)
   {
      if(total_cap_percent <= 0.0)
         return(0.0);

      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      double cap    = equity * total_cap_percent / 100.0;
      double used   = 0.0;

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!m_pos.SelectByIndex(i)) continue;
         if(m_pos.Symbol() != m_sym.Name()) continue;
         if((long)m_pos.Magic() != magic) continue;
         double sl = m_pos.StopLoss();
         if(sl <= 0.0) continue;
         double dist_pts = MathAbs(m_pos.PriceOpen() - sl) / m_point;
         used += dist_pts * m_pos.Volume() * PointValuePerLot();
      }

      double left = cap - used;
      if(left <= 0.0)
         return(0.0);
      return(left / equity * 100.0);
   }
};
//+------------------------------------------------------------------+
