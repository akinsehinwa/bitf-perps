---
name: bitfunded-perps
description: >-
  Bitfunded prop-challenge co-pilot for Binance USDT perpetuals (crypto and
  TradFi perps like XAU, XAG, oil, QQQ, NVDA). Knows the Bitfunded 50K two-step
  rules (stage 1 +8%, stage 2 +5%, 5% max daily loss reset at 00:00 UTC+8,
  10%/8% max loss counting floating P&L, 1:5 leverage, 0.04% fee per side,
  max 5 open positions, margin under 65%, max hold 10/7 days, 2 closed
  trades of 10+ minutes per stage), scans the 4h candle closes at the
  scheduled Singapore times, sizes every trade so a stop-out can never break
  a firm limit, prints the exact ticket to place by hand (side, qty, isolated
  5x, SL, TP), logs fills, tracks stage progress and daily-loss headroom,
  backtests on Binance perp history and tunes risk from results. Use when the
  user says "scan", "any setups", "run the 4h scan", "plan this trade",
  "size it", "I'm in", "I got stopped out", "close it", "where am I in the
  challenge", "daily loss left", "backtest", "tune", "which coins", or
  mentions Bitfunded, the eval, stage 1 or stage 2.
argument-hint: "[scan | status | plan SYM long|short --entry --stop | open | close | backtest | tune]"
---

# bitfunded-perps

This skill does not place orders. Bitfunded has no order API, so the trader
places every order on the Bitfunded platform, with the stop-loss and
take-profit it prints. A setup is a rule match, not a prediction, and most
people who trade leveraged perps lose money. Passing an evaluation is never
guaranteed.

`${CLAUDE_SKILL_DIR}` is this folder. State lives in `./trader/perps/`
(config.json, journal.json, signals.json, markets.json, cache/).

```bash
python3 "${CLAUDE_SKILL_DIR}/perps.py" rules          # firm limits + this tool's stricter guards
python3 "${CLAUDE_SKILL_DIR}/perps.py" scan           # setups on the last closed 4h bar -> tickets
python3 "${CLAUDE_SKILL_DIR}/perps.py" status         # stage progress, daily / max-loss headroom
python3 "${CLAUDE_SKILL_DIR}/perps.py" plan SOL long --entry 150 --stop 144   # manual idea -> ticket
python3 "${CLAUDE_SKILL_DIR}/perps.py" open --signal 1 [--entry FILL]         # log what you placed
python3 "${CLAUDE_SKILL_DIR}/perps.py" close 3 --exit 158.2                   # log the exit
python3 "${CLAUDE_SKILL_DIR}/perps.py" stage 2        # after the firm moves you to stage 2
python3 "${CLAUDE_SKILL_DIR}/perps.py" tune           # adapt risk to recent results (bounded)
python3 "${CLAUDE_SKILL_DIR}/perps.py" markets        # refresh Bitfunded's instrument list + costs
python3 "${CLAUDE_SKILL_DIR}/perps.py" data --all     # Binance perp 4h history (public archive)
python3 "${CLAUDE_SKILL_DIR}/perps.py" backtest --all --detail
```

## The strategy: "4h quality breakout, with BTC"

1. **What:** BTC ETH BNB XRP SOL HYPE ZEC ADA UNI LINK.
2. **When:** three 4h candle closes, Singapore time: 08:00 (daily open),
   20:00 (pre-New York), 00:00 (New York session). No 16:00 scan (it lost
   money in every period). No new entries on Monday (SGT). Nothing from Sat
   04:00 to Sun 20:00 SGT; anything open is closed at Sat 04:00.
3. **Direction:** BTC's 4h trend (EMA 50 vs EMA 200). Up: longs only. Down:
   shorts only. The coin's own trend must agree.
4. **Trigger (4h):** the candle CLOSES above its 55-candle high (long) or
   below its 55-candle low (short), having been inside one candle earlier,
   and its body is at least 1 x ATR(14) (a real push, not a drift).
5. **A+ tag:** 3 or more of the 10 coins break out on the same candle (a
   market-wide move). Historically +0.7 to +0.8R a trade, 67-74% win.
6. **Entry (1h):** a LIMIT order 0.5 x ATR back toward the breakout, valid
   8 hours. Not filled by then: cancel, no trade.
7. **Stop:** the signal close -/+ 2.0 x ATR (1.5 ATR from the limit).
   **Target:** 2R from the fill. **Time stop:** 48 hours after the fill, or
   the weekend close, whichever comes first.
8. **Size:** 1.5% of the account at risk per trade, 0.04% open and close fee
   included, isolated 5x. Max 3 new trades a day.

Backtest Nov 2023 to Nov 2026, 4h signals executed on 1h bars, 0.04% fee
per side, stop first when a 1h bar touches both, no target on the fill bar:
182 trades (about 5 a month), 60% win, +0.48R average, profit factor 2.6.
Last 12 months (traits found on the first two years): 71 trades, 66% win,
+0.56R, profit factor 3.2. Challenge sim at 2%: stage 1 passed 87%
(median 64 days), failed 10%; both stages passed 72% (median 135 days).

Why these filters: of ~15 traits measured on every A trade, only four held
up in both the first two years and the last year: breadth (3+ coins
breaking together), breakout candle body >= 1 ATR, the 16:00 SGT scan
(bad), Monday entries (bad). Rejected: USDT.D and DXY trend, RSI,
volume, distance from EMA, BTC momentum (flipped between periods).

What to tune, in order of evidence (re-run `backtest --detail` after each):
risk (1.5-3%), `min_body_atr`, `target_r`, `atr_stop`. One change at a
time, judged on the last 12 months, never on the full period alone.

## Strategy 2: "4h candle range theory (CRT), with BTC"

Runs in the same `scan`, at the 08:00, 12:00, 16:00 and 20:00 SGT 4h closes
(not 00:00: it lost there), outside the weekend pause.

1. **C1, the range candle:** body at least 70% of its range (small wicks),
   range at least 1 x ATR(14, 4h).
2. **C2, the sweep:** trades beyond one end of C1 and closes back inside it.
   Bullish C1 whose HIGH is swept -> short. Bearish C1 whose LOW is swept ->
   long. Only in BTC's 4h trend direction (so it is a failed counter-trend
   push, i.e. a pullback entry).
3. **Entry:** a STOP order at C2's low (short) / high (long), valid until C3
   closes (4 hours). Not triggered: cancel.
4. **Stop:** beyond C2's sweep wick + 0.1 ATR. **Target:** C1's far end (the
   floor of the range for a short). Skipped below 1R.
5. Same risk, guards, time stop and weekend close as Q; tickets are tagged
   `crt4h` so `tune` reports it separately.

Research, last 3 years, 10 coins, 15m execution, 0.04% fee per side: +0.16R a
trade, 52% win, about 4-5 a month (-0.04 / +0.27 / +0.20R by year). Weaker
than Q and it lost in its first year, so it runs at the same 1.5% risk and
should be cut if `tune` shows it below 0R after 20 trades. Tested and
rejected: entering at C3's open (-0.14R), a 15m CRT as confirmation
(-0.05R), 1h/2h CRT, and requiring the sweep to hit a prior daily or 4h
swing level (no consistent improvement).

Running Q and CRT together (one position per coin, max 3 open, max 3 a
day), challenge sim at 1.5% risk: both stages passed 77%, median 89 days;
at 2%: 55%, median 61 days. Q alone at 1.5%: 92%, median 158 days.

## The pipeline (same shape as the original Day Trader pack)

| step | original skill | here |
| --- | --- | --- |
| 1 scan | trader-scanner | `scan` on the 08/20/00 SGT 4h closes (not Monday), 10 coins |
| 2 news | trader-news | event guard: TradingView `get_economic_calendar` + `get_news` |
| 3 entry | trader-entry | 1h limit 0.5 ATR back from the 4h close, valid 8h |
| 4 exit | trader-exit | ATR stop, R-multiple target, time stop, flat for the weekend |
| 5 replay | trader-timemachine | `backtest`: every past signal + challenge simulation |
| 6 size | trader-budget | `risk_budget` + `size_trade` inside `scan` / `plan` |
| 7 risk | trader-risk | the guards below; a BLOCK means no ticket |
| 8 execute | trader-broker | the trader, by hand on Bitfunded, then `open` |
| 9 alerts | trader-alerts | TradingView `create_alert` at the SL, TP and entry |

## Each scheduled scan, step by step

1. `status` first. If it says TARGET REACHED, close everything and stop.
2. Event guard: call TradingView `get_economic_calendar` for the next 4 hours
   (US, high importance: CPI, PCE, FOMC, NFP, GDP). If one lands within the
   next 60 minutes, take no new entries this scan. Say so.
3. `scan`. For each ticket, confirm on the real perp with TradingView
   `get_ohlcv` (`BINANCE:<SYM>USDT.P`, interval 4h, count 5): the last closed
   bar should match the signal bar within a few tenths of a percent. The
   script reads Binance's spot mirror (`data-api.binance.vision`) because
   Binance's futures API is geo-blocked from this container.
4. Show the ticket: side, LIMIT price and its cancel time, qty, isolated
   5x, SL, TP, loss at stop, gain at target, fees. The trader places the
   limit with SL/TP attached and decides. Never say "buy" or "a winner".
5. After the trader says they placed it: `open --signal N --entry FILL`, then
   offer TradingView alerts at the SL and TP (`create_alert`, price,
   `cross`, `auto_deactivate: true`).
6. When a position closes: `close ID --exit PRICE`. After every 5 closed
   trades: `tune`.

## Data and order hygiene (from the Trading Floor engine)

- **Live feed:** closed perp candles from Binance USDT-M, then Bybit linear,
  then OKX USDT swaps; Binance SPOT only as a last resort. The scan header
  names the feed used. (From this cloud box Binance and Bybit are geo-blocked,
  so it reads OKX perps.)
- **Staleness:** a coin whose latest closed 4h candle is not the one that just
  closed is skipped; stale BTC data stops the whole scan (no tickets).
- **Fees-included target:** take-profit = entry +/- (2 x (stop distance +
  0.08% round-trip fees) + 0.08%), so a hit nets a full 2R after fees. The
  backtest uses the same target.
- **Rounding to Bitfunded's contract:** quantity rounded DOWN to the
  instrument's lot (e.g. BTC 0.001, XRP 10), so the loss at the stop never
  exceeds the budget; stop rounded away from the entry and target toward it,
  to Bitfunded's price precision (`markets` refreshes both).
- **Offered record:** `trader/perps/offered.json`; a setup (coin, strategy,
  side, signal candle) is never issued twice, even if you re-run the scan.

## Guards (all enforced in code)

- Loss at every open stop + realized loss today <= the daily guard (default
  3.5% vs the firm's 5%), so a full stop-out day cannot break the daily rule.
- The same sum against the max-loss floor, with a 1.5% buffer.
- Max 3 open positions (firm: 5), open risk <= the cap, total margin <= 50%
  (firm: 65%), one position per asset, no hedging.
- Max 3 new trades per Bitfunded day (00:00 SGT).
- No entries from Sat 04:00 to Sun 20:00 SGT; positions are closed by Sat
  04:00 SGT.
- Finish-line sizing: near the target, risk shrinks to what the last win needs.
- Profit target counts realized P&L only and needs 2 closed trades held 10+
  minutes; close everything to advance (stage moves 30 minutes after flat).

## Rules

- Say what was scanned and the time of the data (4h bars close at 00, 04,
  08, 12, 16, 20 SGT).
- Never print a profit promise. Backtest numbers are history, not odds.
- Never suggest raising risk above `max_risk_pct`, removing the stop, or
  holding past the time stop to "get back" a loss.
