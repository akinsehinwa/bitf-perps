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

## Check-ins (2026-11-14)

The user checks in every day, weekends included, at 08:00, 12:00, 16:00, 20:00 and
00:00 SGT (`schedule.checkins`); the weekend pause is OFF (`weekend_pause: false`,
`flat_for_weekend: false`). Each strategy still only issues tickets at its own tested
hours and days, re-checked on the new core 10 (research/slots_hours.py, last 12
months | prior 2 years): Q 00:00 +0.49|+0.17R, 08:00 +0.18|+0.30, 20:00 +0.51|+0.17
(04/12/16 weaker), and Q skips Mon (-0.55|-0.16), Sat (-0.11|-0.26), Sun (+0.02|-0.17).
CRT keeps 08-20 and skips Fri (-0.21|-0.35) and Sat. Swing stays off from Sat 04:00 to
Sun 20:00 (never tested). So weekends are mostly quiet by design.

## The strategy: "4h quality breakout, with BTC"

1. **What:** BTC ETH BNB XRP SOL ADA UNI LINK AVAX LTC (since 2026-11-14:
   HYPE and ZEC out, AVAX and LTC in; see "Coin list" below).
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
   **Target:** 1.5R from the fill (after fees; 2R tested +0.43R vs 1.5R +0.41R
   with a higher win rate). **Time stop:** 48 hours after the fill, or
   the weekend close, whichever comes first.
8. **Size (volatility tilt):** 1.75% of the account at risk per trade in the
   eval (1.5% once funded; user's choice 2026-11-14) when BTC's 7-day realized volatility is EXPANDING
   (stdev of the last 42 closed 4h returns above the 42 before), half that
   when it is contracting. Fees included,
   isolated 5x, max 3 open, max 3 new a day, one position per coin. The scan
   header prints the state and the risk.

Backtest Nov 2023 to Nov 2026, 4h signals, 15m execution, limits filled only
if price trades 0.05 ATR THROUGH them, 0.04% fee per side, stop first when a
bar touches both, no target on the fill bar: 181 trades (about 5 a month),
58% win, +0.43R average (expect about +0.42R live). By volatility state:
expanding +0.44 / +0.65R, contracting +0.25 / +0.26R (first 2 years / last
year). The Monte Carlo lie-detector: on shuffled-day synthetic markets Q
makes about +0.05R vs +0.22R on real history (simple 4h engine), so the edge
is real trend structure. All 324 parameter combinations around these
settings were profitable; re-tuning them every 3 months made results WORSE
(+1.41 vs +2.17R a month), so the settings are fixed.

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
5. **BTC daily filter:** BTC's daily EMA20 must agree with the side (EMA20 >
   EMA50 for longs, below for shorts); without it the first year lost money.
6. **Size:** 0.75 x Q's: 1.125% (volatility expanding) / 0.56% (contracting),
   with 0.05% stop-order slippage built into the size. **Time stop:** 24h.
   Weekend close as Q. A coin that already has a Q ticket in the same scan is
   skipped (one position per coin); tickets beyond the free slots are skipped.
   Tagged `crt4h` so `tune` reports it separately.

Research, last 3 years, 10 coins, 15m execution, stop orders triggered on a
TOUCH and filled at the trigger + 0.05% slippage (honest model), BTC daily
filter: 99 trades (2.7 a month), 58% win, +0.30R, profit factor 1.74;
-0.04 / +0.45 / +0.40R by year; +0.29 / +0.31R on the 70/30 split. On
probation: cut it (`"crt": {"enabled": false}`) if `tune` shows it below 0R
after 20 trades. Rejected: entering at C3's open, a 15m CRT confirmation,
1h/2h CRT, sweeps into prior daily/4h levels.

## Strategy 3: "swing" (big-leg 50% retracement + 1h inverted FVG), all coins

Runs in the same `scan` at the 08:00, 12:00, 16:00 and 20:00 SGT check-ins, on ALL
Bitfunded crypto perps (72), not just the core 10.

1. **Swings:** on 1h bars, a swing low (high) only counts once price retraces at
   least 50% of the leg into it; smaller bounces just extend the leg. Legs are
   read over the last 5 days.
2. **Parent leg:** at least 7 x ATR(14, 4h), starting at a lower high and ending
   at a lower low for a short (higher low -> higher high for a long).
3. **Arm:** the 50% retracement of that leg. Void if a 1h candle closes beyond
   the 78.6% retracement or after 48 hours.
4. **Trigger:** a 1h fair value gap formed during the retracement is inverted (a
   1h close through it) between the previous check-in and this one.
5. **Ticket:** LIMIT at the gap's midline, valid 12 hours. Stop beyond the
   retracement extreme + 0.5 x ATR(4h). Target 1.5R after fees. Risk 0.5 x the
   stage risk (0.75% in the eval, 0.5% funded); no volatility tilt. Time stop 96h.
   Skipped if the stop already traded, or the coin already has a Q/CRT ticket.

Research (research/ifvg2.py, swing_checkin.py, book_swing.py), all 72 coins, entry
at the next check-in: last 12 months 173 trades (14/month), 49% win, +0.16R; the
2 years before +0.16R. Core 10 alone ~0R lately, so the edge is spread across the
market. With Q + CRT: eval pass ~93% (vs 95%), median ~100 days (vs ~149). At full
size: 76% pass, so keep it at half. The live detector was replayed against the
backtest on 12 coins (60 days): same tickets.

## Ticket sizing menu

Every ticket ends with: what it was sized for (account, stage, risk %), the SL and TP as price % and as
% of margin at 5x, and a table of the USDT margin to enter (and qty) at 0.5 / 1 / 1.5 / 1.75 / 2 / 2.5% risk
for 50K and 100K accounts, capped at Bitfunded's per-coin max position (marked *). The user picks the
cell for the account and risk they are trading.

## Ticket order: setup grade (all strategies)

Every ticket carries a grade from its running room: the distance from the entry
to the nearest untouched 4h swing in the trade direction, in R.
**A+** = 3R or more of room (backtest +0.53R/trade); **A** = clear air or
blocked under 1.5R (+0.39 / +0.41R: breakouts often run straight through);
**B** = 1.5-3R (+0.25R). Tickets print best-first (grade, then Q, CRT, swing).
The grade orders tickets; it never skips one. Take every ticket the slots allow:
capping to the first 1-2 a day halved profit (the busiest days are the best).

## Coin list (2026-11-14)

All 72 Bitfunded crypto perps were run through Q and CRT. Q's per-coin results
track how closely a coin follows BTC (rank-corr +0.47) and fall with volatility
(-0.35). HYPE (CRT -0.46R) and ZEC track BTC least of the old core and were
dropped; AVAX and LTC (BTC correlation 0.73 / 0.71, volatility 72% / 56%) were
added. Last 12 months: 107 trades, +0.55R, +4.9R a month, max drawdown 8.4R.
The other 62 coins: Q +0.15R, CRT about 0R; all 72 at once would fail an eval
on a bad month (worst 5% month -26R).

## What to expect (both strategies together)

Challenge simulation (2026-11-14 settings: 10 coins above, 1.5% eval risk with
the volatility tilt, CRT x0.75, guards below), realistic fills, 3 years of
history: both stages passed about 95% of rolling start dates, median ~149 days,
about 155 days per funded account counting retries. Forward Monte Carlo from the
last 12 months (flat 1.5%, no guards): 1 month median +1.4R (5% worst -3.4R),
3 months median +9.8R (65% chance of +8%), 6 months median +23R. Funded at 1%:
about +$570 a month to you at the median (80% split), worst 5% -$1.4k. There is no setting that reliably passes
in two weeks; raising risk mostly raises the failure rate. Results are
history, not a promise.

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
| 8 execute | trader-broker | the trader, by hand on Bitfunded (limit / stop tickets), then `open` |
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
  0.08% round-trip fees) + 0.08%) with R = 1.5, so a hit nets 1.5R after fees. The
  backtest uses the same target.
- **Rounding to Bitfunded's contract:** quantity rounded DOWN to the
  instrument's lot (e.g. BTC 0.001, XRP 10), so the loss at the stop never
  exceeds the budget; stop rounded away from the entry and target toward it,
  to Bitfunded's price precision (`markets` refreshes both).
- **Offered record:** `trader/perps/offered.json`; a setup (coin, strategy,
  side, signal candle) is never issued twice, even if you re-run the scan.

## Guards (all enforced in code)

- Loss at every open stop + realized loss today <= the daily guard (default
  4.25% vs the firm's 5%), so a full stop-out day cannot break the daily rule.
- The same sum against the max-loss floor, with a 1.0% buffer.
- Max 3 open positions (firm: 5), open risk <= 4.5%, total margin <= 60%
  (firm: 65%) and <= 30% per position, one position per asset, no hedging.
- Max 3 new trades per Bitfunded day (00:00 SGT).
- No entries from Sat 04:00 to Sun 20:00 SGT; positions are closed by Sat
  04:00 SGT.
- Finish-line sizing is OFF (it slowed passes in the 2026-11-13 risk study);
  risk halves while the stage is down more than 3%.
- Profit target counts realized P&L only and needs 2 closed trades held 10+
  minutes; close everything to advance (stage moves 30 minutes after flat).

## Rules

- Say what was scanned and the time of the data (4h bars close at 00, 04,
  08, 12, 16, 20 SGT).
- Never print a profit promise. Backtest numbers are history, not odds.
- Never suggest raising risk above `max_risk_pct`, removing the stop, or
  holding past the time stop to "get back" a loss.
