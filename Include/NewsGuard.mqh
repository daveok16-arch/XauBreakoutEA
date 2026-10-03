//+------------------------------------------------------------------+
//|                                               NewsGuard.mqh      |
//|   Blocks trading around high-impact calendar events.              |
//|   Uses the terminal's built-in economic calendar (no DLL, no      |
//|   external URL) so it is Marketplace-compatible.                  |
//+------------------------------------------------------------------+

class CNewsGuard
{
private:
   string m_symbol;
   string m_currency;
   int    m_before_min;
   int    m_after_min;

   //--- map a symbol like XAUUSD / XAUUSD.a / GOLD to its base currency
   string BaseCurrency(void) const
   {
      string s = m_symbol;
      // strip common suffixes
      StringReplace(s, ".a", ""); StringReplace(s, ".m", "");
      StringReplace(s, ".raw", ""); StringReplace(s, ".pro", "");
      StringReplace(s, "-ECN", ""); StringReplace(s, "micro", "");
      if(StringFind(s, "XAU") == 0 || StringFind(s, "GOLD") >= 0)
         return("USD");   // gold is quoted in USD; USD events move it hardest
      if(StringLen(s) >= 6)
         return(StringSubstr(s, 0, 3));
      return(s);
   }

public:
                     CNewsGuard(void) { m_before_min = 0; m_after_min = 0; }

   bool              Init(const string symbol, const int before_min, const int after_min)
   {
      m_symbol     = symbol;
      m_before_min = before_min;
      m_after_min  = after_min;
      m_currency   = BaseCurrency();
      return(true);
   }

   //--- true when we are inside the no-trade window of a high-impact event
   bool              IsBlocked(void)
   {
      if(m_before_min <= 0 && m_after_min <= 0)
         return(false);

      MqlCalendarValue values[];
      datetime from = TimeCurrent() - 3600 * 6;
      datetime to   = TimeCurrent() + 3600 * 6;

      if(!CalendarValueHistory(values, from, to, NULL, NULL))
         return(false);

      int n = ArraySize(values);
      for(int i = 0; i < n; i++)
      {
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id, ev))
            continue;
         if(ev.importance != CALENDAR_IMPORTANCE_HIGH)
            continue;

         MqlCalendarCountry country;
         if(!CalendarCountryById(ev.country_id, country))
            continue;
         if(country.currency != m_currency)
            continue;

         datetime t = values[i].time;
         if(TimeCurrent() >= t - m_before_min * 60 &&
            TimeCurrent() <= t + m_after_min * 60)
            return(true);
      }
      return(false);
   }
};
//+------------------------------------------------------------------+
