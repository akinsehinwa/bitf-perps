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
7. Compare to the baseline book: Q (4h quality breakout, 10 coins) 2% + CRT 4h (BTC daily trend) 1%, with
   the BTC 7-day-volatility tilt (Q 2.5% when vol expanding / 1.25% contracting).
   Baseline (rolling challenge sim): both stages 91%, median ~81 days.
8. Write results and the decision to /home/user/bitfunded-perps/research/LEDGER.md (append, dated).
