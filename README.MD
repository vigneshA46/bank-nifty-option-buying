The banknifty_option_buying strategy is an intraday option buying system built on Bank Nifty, where strike selection is done using the Bank Nifty index and execution is done in options. The ATM strike for both CE and PE is selected from the close of the first 1-minute Bank Nifty candle. For each option, the close of its first 1-minute candle is marked as a reference line. A buy entry is triggered when a candle closes above this marked line and the average price is above the line but below the candle close, with execution on the next candle; additionally, an entry is also allowed if any tick moves more than +25 points above the marked line without obeying the average price rule. Exits occur if a candle closes below the marked line or if any tick moves 25 points below it.

Each trade uses a trailing stop-loss system where TSL starts at +40 points from entry, SL is placed 15 points below the TSL, and TSL activates only after price touches it; as the market moves, both TSL and SL trail upward by 10 points. Lot sizing is progressive and merged across CE and PE: the first trade of the day starts with 1 lot, and every new trade—regardless of CE or PE—increases the lot size by 1, freezing at a maximum of 5 lots. If a trade exits via TSL, the lot size resets back to 1 and then starts increasing again on subsequent trades. If a trade has its TSL activated and later exits at SL, the next entry on that option is allowed only after price moves back below the marked line and re-qualifies.

Universal exits apply where all positions are closed and trading stops once cumulative profit reaches 100 points, or when the time reaches 15:20, whichever comes first.



✅ SHEET 1 — BankNiftyLogger (DAY / SESSION LOGS)

This sheet stores session-level information, not individual trades.

📄 Columns
Column Name	Purpose
Date	Trading date
Strategy	banknifty_option_buying
ATM	Calculated ATM strike
StartTime	Engine start time
EndTime	Engine stop time
TotalTrades	Number of trades
CETrades	Number of CE trades
PETrades	Number of PE trades
DayPNL	Final PNL
MaxProfit	Max cumulative profit reached
MaxDrawdown	Worst drawdown
ExitReason	TARGET_HIT / TIME_EXIT / MANUAL
Notes	Optional remarks
✅ SHEET 2 — BankNiftyTrade (TRADE BOOK)

This stores every entry + exit.

📄 Columns
Column Name	Purpose
Timestamp	Entry/Exit timestamp
Symbol	BANKNIFTY
OptionType	CE / PE
SecurityID	Option security id
Side	BUY / SELL
EntryPrice	Entry price
ExitPrice	Exit price
Lots	Lots used
Qty	Lots × lot size
PNL	Trade pnl
CumulativePNL	Running pnl
EntryReason	CandleBreak / TickBreak
ExitReason	MarkedLine / TickSL / TSL / Time
MarkedLine	First candle close
TSL	Final tsl
SL	Final sl