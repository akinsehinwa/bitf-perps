# Maybe vault: promising strategies, not live

Ideas that showed a real edge but can't go into the ticket book yet. Each entry has the evidence, what blocks it,
and what would make it worth re-testing. Re-check vault items when the blocker changes, or every few months on the
latest 12 months of data (house standard: last 12 months first, the 2 years before as the stability check).

## Strategy roster

| Strategy | Status | Universe | Timeframe / entry | Last 12m (backtest) | Notes |
|---|---|---|---|---|---|
| **Q** - 4h quality breakout with BTC | LIVE | core 10 | 4h close, limit 0.5 ATR back, 1.5R | +0.65R, ~1.4/week | not Mon/Sat/Sun; 08/20/00 SGT |
| **CRT** - 4h candle range sweep | LIVE | core 10 | 4h, stop-entry at C2 extreme, range target | +0.56R, ~0.5/week | 08-20 SGT; not Fri/Sat |
| **Big-leg swing** - 50% retrace + 1h inverted FVG | LIVE (half risk) | all 72 | limit at FVG midline, 1.5R, 96h | +0.16R, ~3.3/week | 08-20 SGT check-ins; off Sat 04:00-Sun 20:00 |
| **SuperTrend** - both sides, BTC filter, 7-day cap | VAULT (promising) | all 72 | daily flip, trailing stop on the line | +0.27R (10,2) | blocked by hold limit + slots, see below |

## SuperTrend (both directions, BTC filter) - PROMISING (added 2026-11-21)

**Rule:** daily SuperTrend (ATR 10). Long when the close flips above the line, short when it flips below. Only
in the direction BTC's own daily SuperTrend points. The SuperTrend line is the trailing stop (hit intrabar).
Close by day 7 (Bitfunded max hold). Scripts: `research/qs2.py`, `research/qs2_st.py`.

**Evidence (all 72 Bitfunded crypto perps):**

| Version | Last 12 months | 2 years before | Trades/month |
|---|---|---|---|
| (10,3), both sides, no cap | +0.10R | +0.22R | ~45 |
| (10,3), BTC filter, 7-day cap | +0.12R | +0.07R | ~25 |
| (10,2.5), BTC filter, 7-day cap | +0.18R | +0.08R | ~25 |
| **(10,2), BTC filter, 7-day cap** | **+0.27R** | **+0.09R** | ~33 |
| (10,3) long only, no cap, as published | -0.01R | +0.79R (core +1.60R) | ~21 |

Core 10 alone is mixed (-0.07R to +0.34R by setting).

**Why it isn't live:**
1. Its real edge needs long holds (median 26 days, 1 in 10 over 75 days). Bitfunded caps positions at 7-10 days;
   the cap removes most of the edge. Closing at day 7 and re-entering ("rolling") gave only +0.02 to +0.14R.
2. ~25-35 trades a month, each sitting up to 7 days, would fill the 3 position slots and crowd out Q / CRT / swing,
   which earn more per trade.
3. About 10 variants were tried, so the best one is partly selection luck.

**Re-test / adopt if:** a separate account is run just for it (no slot conflict), Bitfunded relaxes the max hold,
or a slot-light version appears (e.g. core 10 only, or only the first flip per week). First check would be a full
challenge simulation of Q + CRT + swing + SuperTrend on a second account.

## Other watch items (weaker)

- **Bollinger 20 + 1h engulfing** (`bb_lab.py`): +0.13R with a 1h entry, but the reviewer found the engulf timing
  adds nothing and every check-in / limit-order version fades out-of-sample. Only revisit with a new entry idea.
- **User's discretionary swing method** (journal in `journal/discretionary.csv`): judge after ~30 logged trades
  with stop prices; the mechanical big-leg version is already live as the swing strategy.
- **Q with a 3R target**: +0.47R vs +0.43R at 2R in one test; within noise, not pursued.
