# House rules for every research role (read first)

Goal: raise the probability of passing the Bitfunded 50K two-step (stage 1 +8% / -10%, stage 2 +5% / -8%,
-5% daily, losses include floating P&L, day resets 00:00 SGT) and shorten the time to pass, with trades the
trader places BY HAND from tickets on a 4h clock (scans 08:00 / 20:00 / 00:00 SGT; no entries Sat 04:00 -
Sun 20:00 SGT).

Data: Binance USDT-M perps cached in /home/user/bitfunded-perps/trader/perps/cache/ (<SYM>-4h/1h/15m.json,
<SYM>-funding.json, <SYM>-metrics.json = 5m OI/ratios). Engine: /home/user/bitfunded-perps/perps.py.
Research helpers: /home/user/bitfunded-perps/research/ (qlab.py = Q signals + 15m execution lab,
book2.py = multi-strategy book + challenge simulator, daily.py = daily bias, family.py, crt3.py).

Non-negotiables for any test:
1. No look-ahead: only candles CLOSED before the decision; filters use the prior closed bar/day.
2. Costs: 0.04% fee per side (Bitfunded); no spread. Limit fills need price to trade THROUGH the limit by
   0.05 ATR. Stop first when a bar touches both; never a target on the fill bar.
3. Window: last 3 years (12 Nov 2023 - 13 Nov 2026). Report BY YEAR and the 70/30 split
   (in-sample to 18 Dec 2025). An idea must be positive in BOTH halves.
4. Report: trades, trades/month, win %, avg R, profit factor, R/month, max drawdown (R).
5. Count every variant tried. More than ~20 variants on one idea = treat the best as luck (deflate it).
6. A filter is only useful if R/month or the pass rate improves - a better avg R on fewer trades is not enough.
7. Compare to the baseline book built from research/book_trades_v2.pkl (house Q execution: 15m fills,
   pen 0.05 ATR): Q (4h quality breakout, 10 coins) + CRT 4h (BTC daily trend), BTC 7-day realized-vol tilt
   (Q 2.0% expanding / 1.0% contracting, CRT 1.0% / 0.5%). book2.book defaults, sim window START+10d ..
   START+1005d. CRT fills: stop orders trigger on a TOUCH and fill at the trigger (or the gap open)
   + 0.05% slippage (the pen rule is for limit orders only).
   Baseline: rolling 95% pass, median ~146-151 days; Monte Carlo 90-91%, median ~127 days.
   Standard Monte Carlo = research/review/mc.py method: 3000 paths, 60-week horizon, weekly blocks drawn
   from START+10d..START+1005d, seed 7. ALWAYS report both the rolling sim and this Monte Carlo.
8. Write results and the decision to /home/user/bitfunded-perps/research/LEDGER.md (append, dated).
