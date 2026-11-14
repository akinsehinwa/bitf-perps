# Research ledger

| date | hypothesis | result (3y, by year) | book effect | decision |
| --- | --- | --- | --- | --- |
| 2026-11-14 | Q 4h quality breakout (10 coins) | +0.48R, 60% win, +0.35/+0.47/+0.59; 324/324 grid combos positive | baseline | ADOPT |
| 2026-11-14 | CRT 4h + BTC 4h trend | +0.16R; -0.04/+0.27/+0.20 | Q+CRT faster (88 vs 116 days) | ADOPT (probation) |
| 2026-11-14 | CRT + BTC daily EMA20/50 | +0.22R; +0.04/+0.28/+0.31 | | ADOPT |
| 2026-11-14 | Limit fill stress (pen 0.05-0.1 ATR) | Q +0.47 -> +0.42R | realistic expectation | ADOPT pen 0.05 |
| 2026-11-14 | Entry models (mkt, retest, FVG, body %, split) | all worse than 0.5 ATR limit | | REJECT |
| 2026-11-14 | Walk-forward re-tuning | +1.41 vs +2.17 R/mo fixed | | REJECT (keep fixed) |
| 2026-11-14 | Meta-labeling (logistic, walk-forward) | +17% R per unit risk, unstable ranks | | REJECT (complexity) |
| 2026-11-14 | BTC 7d vol tilt (Q 2.5% expanding / 1.25% contracting) | Q exp +0.57/+0.67 vs contr +0.27/+0.30 | pass 79% -> 91% | ADOPT |
| 2026-11-14 | OI-jump filter (Q), taker filter (CRT) | Q +0.61R; CRT +0.34R | not additive with vol tilt | PROBATION |
| 2026-11-14 | RS rotation, funding fade, squeeze, session drift, CME gap, overnight stops, P50 bot, Roboquant PDH/PDL, VWAP, EMA/StochRSI, S/R flip, 1h/30m Q | ~0R or negative | | REJECT |
| 2026-11-14 | H2 BTC dominance (BTC.D vs EMA10/20/50) as alt regime | alt-friendly not better; flips by EMA length and period (e.g. Q alts EMA20: +0.48/-0.03 friendly vs +0.38/+0.83 hostile) | not tested | REJECT |
| 2026-11-13 | H3 extra-coin Q (61 coins, pen 0.05) gated by regime: BTC vol expanding / vol top-third / core breadth>=3 / liq>=$100M (12 variants, h3_regime.py) | all +0.20R (-0.07/+0.21/+0.41, IS +0.08 OS +0.46); breadth>=3 +0.58R (+0.47/+0.38/+0.80, IS +0.37 OS +0.84) 5.4/mo; vol gates and liq floor do not help | in book W is crowded out: br3 only 13 W trades fill (+0.63R), book +2.08 vs +1.92 R/mo; tilt sim pass 99% both, median 98d vs 96d baseline (same caps, max_same_dir=2) | REJECT as book add-on (no pass/speed gain); breadth>=3 edge real standalone - note for slot-priority idea |
| 2026-11-13 | Q dead-zone sizing: skip Q when BTC 7d realized vol contracting AND BTC DVOL 168h change < 0 (else Q 2.5%); CRT 1.5% vol-expanding / 0.5% else. Reviewer re-run with regime at SIGNAL close (closed bars/hourly DVOL rows only; CRT at 4h boundary <= t_in-4h), scratchpad/rev/dz.py + mc.py | signal- vs fill-time differs on 1 of 181 Q trades. Q (qlab atr:0.5 pen 0.05, no caps) dead zone vs elsewhere: Y1 -0.13 (13) / +0.41; Y2 -0.15 (12) / +0.54; Y3 +0.12 (11) / +0.65; IS -0.13 (26) / +0.48, OS +0.12 (10) / +0.65 | book2.book defaults (max 3, 3/day, 1/coin, no max_same_dir), sim starts START+10d..+1005d, identical settings both arms. Claimed 91% -> 95% (median 81d both) reproduces ONLY with book_trades.pkl Q (old 1h execution, +0.48R; 136/181 trades differ from qlab 15m pen 0.05). With the house Q (qlab pen 0.05): base 83% / 131d vs dead-zone 80% / 93d. 3000-path weekly-block MC (60 wk): pickle Q 88.4% vs 88.4% (median 89 vs 84d); qlab Q 81.5% vs 83.1% (98 vs 92d). Tester's 99% = max_same_dir=2 + CRT flat 1% + earlier cutoff (END-120d) | REJECT as a sizing rule: ~14 variants on a 2-indicator conjunction; dead-zone cell n=11 OS is still positive; pass gain vanishes in MC and reverses with the house Q execution. Keep only as a speed note (median -5..-38d) - not robust. Also: book_trades.pkl Q is stale vs qlab pen 0.05; regenerate it before any further book comparison |
| 2026-11-14 | BASELINE CORRECTION (reviewer): book_trades.pkl Q used the old 1h touch-fill execution | house Q (15m, pen 0.05): 181 trades +0.43R 58% win; vol effect holds (+0.44/+0.65 expanding vs +0.25/+0.26 contracting) | Q1.5+C1: 88% / 139d (MC 92% / 133d); tilt Q2.0/1.0 C1.0/0.5: 95% / 151d (MC 92% / 126d); tilt 2.5/1.25: 83% / 116d (MC 86% / 91d) | earlier 91%/81d figures were optimistic; use research/book_trades_v2.pkl |
| 2026-11-14 | DVOL rules (change, percentile, IV-RV spread) and dead-zone skip | dead zone weak both periods but small n (26/10); reviewer: gain vanishes in MC and with house Q | none after deflation (~14 variants) | REJECT |
| 2026-11-13 | Cycle 2 CRT re-check, realistic stop fills (research/cycle2_crt.py, 10 variants): pen 0.05 ATR + slip 0.02/0.05%, 1R on fill, fee 0.04%/side, BTC daily EMA20/50 filter, scan hours | live hrs 08/12/16/20 SGT + daily: old fill +0.29R (+0.02/+0.37/+0.46; IS +0.27 OS +0.38) 3.1/mo +0.89R/mo; pen+slip .02 +0.42R (+0.05/+0.57/+0.63) 2.6/mo +1.09R/mo; pen+slip .05 +0.42R 2.4/mo. LOOK-AHEAD/SELECTION FLAG: the pen rule drops 16 touched-then-reversed trades (avg -0.54R) - a real stop order triggers on touch, so pen flatters stop entries. Conservative touch+slip .05: +0.30R, 58% win, PF 1.74, +0.81R/mo, DD 4.5R, -0.04/+0.45/+0.40, IS +0.29 OS +0.31. No daily filter: Y1 negative in every fill model. Hours: "all except 00/04" = the live set; all 6 closes old +0.22R +0.92R/mo; adding 04 helps a bit (real .02 +1.21 vs +1.09R/mo) | same MC script, baseline v2 Q+C: 95%/151d, MC 90.1%/127d. Q only tilted: 95%/186d, MC 86.8%/156d. Q+CRT touch .05 (live hrs, daily): 95%/146d, MC 91.3%/128d. Q+CRT pen .02: 95%/135d, MC 94.5%/126d (optimistic) | KEEP CRT (earns place: -40d median, +4.5pt MC vs Q only) at 1.0/0.5% with BTC daily filter, live hours; book it with the touch+slip model, not pen. Y1 still ~0R - stays on probation |
| 2026-11-13 | Cycle 2 slot priority ("ticket desk"): allocate slots at SIGNAL time, rank simultaneous tickets; pending tickets hold a slot until fill/expiry (Q/W 8h, CRT 4h); max 3 slots, 3 placed/day, 1/coin. 7 variants: a fill-FCFS (baseline), b desk FCFS, c breadth>Q>W>C, d E[R]/ticket by strat x BTC vol (IS < 2025-11-12), e c+W, f d+W, g b+W (W = h3 breadth>=3). cycle2_slots.py | regenerated Q 181 / C 150 trades identical to book_trades_v2.pkl. a: 7.7/mo +0.26R +2.02R/mo DD 9.1 (IS +1.88 / OS +2.33 R/mo); b=c=d: 7.4/mo +0.25R +1.82R/mo DD 10.2 (+0.13/+0.23/+0.38); e/g: +1.87R/mo DD 11.7, only 9 W fill; f: 15 W, +1.86R/mo | rolling / MC(60wk, 3000 paths, seed 7): a 95% 151d / 90.1% 127d; b,c,d 95% 155d / 85.6% 146d; e,g 89% 128d / 85.4% 135d; f 85% 124d / 85.4% 135d | REJECT. Ranking is moot: only 26 of 325 decision times mix strategies; 294 of 330 W tickets arrive with all 3 slots already held (positions last up to 48h), so ranking cannot reach them. Reserving slots for unfilled tickets (37-38% never fill) costs ~0.2R/mo and ~5 pts MC pass. Keep fill-time FCFS. Note: ledger MC 92%/126d not reproduced exactly; rev/mc.py method gives 90.1%/127d for the same baseline |
| 2026-11-14 | BUILD: skill updated - Q risk 2%/1% by BTC 7d vol; CRT + BTC daily EMA20/50 filter, half size, 0.05% stop slippage, 24h exit; backtest fills need 0.05 ATR through the limit; sim sizes by vol state; one ticket per coin per scan, tickets capped to free slots | expectation: Q+CRT rolling 95% / ~146d, MC 91% / ~128d | | LIVE |
| 2026-11-14 | QUEUED (user idea): DVOL spike + weekly RSI + historically oversold price -> dip-buy longs | not tested; slow (weeks), rare, conflicts with 10-day hold | | NEXT CYCLE |
| 2026-11-13 | Cycle 3 idea 3: daily TS momentum (close > 20d/55d closing high + daily EMA50 slope, opt. BTC EMA20/50), 4h-clock LIMIT 0.5 ATR(d) / 1.0 ATR(4h) back, valid 24h, pen 0.05, stop 2.0/1.5 ATR(d), 3R/2R after-fee or 10d-low trail, 9d max, weekend flat vs hold. 10 standalone variants + 4 book arms (research/cycle3_daily_trend.py) | core V1 (N20, 0.5ATRd, 2ATR, 3R, flat): 569 tr 15.8/mo 41% win -0.04R PF 0.88 -0.63R/mo DD 34R (Y -0.12/+0.02/-0.02; IS -0.06 OS -0.00). Weekend flat kills it (422/569 exit at Sat 04:00; 3R hit 13x). Best: V9 trail+hold +0.03R +0.35R/mo (Y1 -0.08, IS -0.02 OS +0.13); V8 hold IS -0.05 OS +0.11; V5 4h entry IS -0.04 OS +0.05. IS-selected combo V10 (N55 BTC 4hATR trail hold): IS +0.07 OS -0.03 (n=68). No variant positive in both halves. Overlap with Q: 51-77 trades same coin/side/time | baseline 95%/151d, MC 90.1%/127d. +V1 @1%: 79%/253d, MC 56.5%/150d; tilt 1/0.5: 86%/209d, MC 61.6%. +V10 @1%: 72%/150d, MC 63.6%; tilt: 92%/175d, MC 70.8%/155d (N crowds Q/CRT out of slots; book R/mo 2.02 -> 0.8-1.3) | REJECT. Weekend-hold trend variants show OS-only edge (Y1 strongly negative) - not robust, conflicts with the flat-weekend rule |
| 2026-11-13 | Cycle 3 ideas 4+5 (trader), research/cycle3_sd_rvol.py, 14 variants. (4) 4h supply/demand zone retest: impulse 1-3 trend candles >= 2.5 ATR from a base <= 1.2 ATR (1-4 bars), resting limit at zone near edge for 30 bars, pen 0.05 ATR, stop far edge +/- 0.25 ATR, 2R/3R, 48h; +/- BTC 4h trend, +/- coin daily EMA20/50 (8 variants). (5a) RVOL >= 3/4 climax wick fade after >= 3 ATR/6-bar move, limit 0.25 ATR back, 2R, 24h (2). (5b) CRT only when C2 RVOL >= 1.5/2, honest touch+0.05% and v2 CRT (4) | SD wick 2R -0.06R 35% win 6.6/mo (-0.06/-0.10/-0.02; IS -0.05 OS -0.08); all 8 SD variants negative in every year and both halves (best filtered 4.7 -0.08R; body zones -0.19..-0.24R). Climax RVOL>=3 -0.02R 2.8/mo (+0.01/+0.27/-0.46; IS +0.11 OS -0.43); >=4 -0.11R 1.3/mo. CRT RVOL filter raises avg (touch +0.30 -> +0.54R n=12; v2 +0.22 -> +0.42R n=30) but R/mo falls (+0.81 -> +0.18; +0.92 -> +0.35), n tiny, OS n=1-7 | baseline 95%/151d, MC 90.1%/127d (Q + honest CRT 95%/146d, MC 91.3%/128d). SD add-on: rolling 48-93%, MC 56-73% (best 4.6 w/ honest C 93%/159d, MC 73%). Climax add-on: 93-94% / 130-149d, MC 86.9-89.1%. CRT RVOL-filtered: 95% / 165-177d, MC 87.8-90.4% / 148-155d (slower) | REJECT all three. SD zones no edge at 4h on these coins; climax fade fails OS; RVOL on CRT = better avg on far fewer trades (rule 6) and +15-30d slower |
| 2026-11-13 | Cycle 3 idea 1 CAP (trader's dip-buy): BTC DVOL pct>=85% of 365d OR +25%/7d, coin weekly RSI<35, daily close < BB(20,2.5) OR 30d drawdown bottom 10%, 4h close > prior high, limit 0.5 ATR/8h, stop 6-bar low -0.1 ATR (>=1.5 ATR), 2R, 9d hold through weekends; 7 variants + 7 checks (research/cycle3_capitulation.py) | 1a: n=34, all in Y3/OS (IS n=0), 35% win, -0.16R, PF 0.76, DD 14.5R; 3R -0.20R; R<40 -0.09R (IS n=5); shorts mirror -0.18R; weekend-flat -0.39R. Longer history (no DVOL; 2022-2026): no fear filter -0.11R (2022 -0.18R n=53); BTC RV top-15% proxy +0.03R (2022 -0.31R, 2026 +0.16R) | baseline 95%/151d, MC 90.1%/127d. +1a @1%: 94%/155d, MC 83.5%/124d; @0.5% 95%/151d, MC 88.9%. Alone @1/1.5/2%: rolling 0%, MC 0.6/1.4/3.5% | REJECT (negative standalone and in every proxy year; too rare - weekly RSI<35 never fired in 2024-25) |
| 2026-11-13 | Cycle 3 idea 2 FLUSH: 4h OI drop >=X% + wick>=50% at a new 24h extreme -> fade; limit k ATR/8h, stop wick +0.1 ATR, 2R, 48h, weekend flat; 8 variants (X 3/5/8, k .25/.5, all vs 08-00 SGT closes, BTC trend) | best on IS 2e (X5 k.5, skip 04 SGT): n=47 1.3/mo 51% win +0.26R PF 1.81 DD 2.6R; Y +0.26/+0.58/-0.23; IS +0.32 (41) OS -0.11 (6). Longs +0.43R (OS n=3, 0.00R), shorts -0.29R. X3 negative, X8 n=21 (OS n=1) | +2e @1%: 95%/122d, MC 92.5%/114d; @0.5%: 95%/137d, MC 91.1%/121d | REJECT for now (fails OS, n tiny, IS-selected from 8); WATCH: paper-track X5 long flushes and re-test with 6+ months more OS |

## 2026-11-13 Speed / extraction cycle
- Trade management on Q (181 live trades, pen 0.05): target 0.5R win 74% but +0.15R; 1R +0.31R; 1.5R +0.41R;
  2R +0.43R (live); 3R +0.47R. Break-even at 0.5R cuts every variant (2R: +0.26R). Partial at 1R: 2R -> +0.37R.
  REJECT lower targets / BE / partials: higher win rate, lower R/month.
- Looser Q signals (Mon on, 6 scans, body 0.5-0.75, Donchian 20/30, no regime): more trades, same or lower R/month,
  drawdowns 1.5-6x bigger; the full loose set is ~0R. REJECT. The original cuts were removing ~zero-edge trades.
- Fast-pass eval (abandon when stuck at the floor): Q5% (caps bind ~5%): 63% pass, median 51d, 15% within 30d,
  E[days] 94, E[fees] $635 vs safe Q1.5 95% / median 173d / E[days] 194 / $420.
- Funded blow-acceptable (180d, 15d payouts): safe Q1.5 $7.1k, $41/day alive, 9% blown; aggr Q5 $9.9k, $108/day,
  83% blown by ~92d. Scripts: speed_lab.py, fast_pass.py, pipeline.py.
- Limit-safe profiles (limit_safe.py; losing trades cost 1.05x / 1.25x planned risk). 5%/trade leaves no slippage room:
  funded blown 100% in ~37d ($3.6k). 3% single position: eval 76% pass, median 80d, E[days] 117; funded $7.3k/180d,
  78% blown. Safe 1.5%: eval 85%, median 163d; funded $6.8k/180d, 14% blown. Plan: pass fast (3% single), milk slow (1.5%).

## 2026-11-14 User strategy: 4h parent leg -> 50/61.8% -> 1h inverted FVG -> limit at midline (ifvg_lab.py)
- 8 user coins (SUI UNI BTC ETH SOL NEAR ADA LINK), 1h execution, pen 0.05, stop at the retracement extreme, 2R.
- Base (zigzag 2 ATR, leg >= 3 ATR): 1149 trades, 32/mo, win 34%, -0.07R. 21 variants (targets, stops, BTC filter,
  windows): all <= 0 except very large legs (>= 8 ATR). ifvg_big.py: k3 G8 +0.11R 5.4/mo but IS +0.01 / OS +0.45,
  year 1 -0.15; neighbours (G6/G10, k2.5/k4) scatter around 0; other 4 coins -0.07R. Winners by coin (SUI ETH ADA)
  look like selection. REJECT as a mechanical rule; big-leg pocket on WATCH (positive only in 2026).

## 2026-11-14 Trade management lab (manage.py) - Q, CRT, iFVG rules, iFVG big legs
- Full-stop losers that first reached +1R: Q 10%, CRT 5%, iFVG 16-19%. BE at 1R rescues those but stops out ~3-4
  winners per rescue: Q +0.43 -> +0.36R, CRT +0.34 -> +0.28R, iFVG big +0.11 -> +0.07R. BE 0.5R worse; BE 1.5R ~neutral.
- Partials (half at 0.5R/1R, with/without BE) raise win rate, cut avg R 15-50%, barely change 10-trade worst streaks.
- 3R helps Q (+0.47R) but hurts CRT. No rule turns the iFVG rules positive. VERDICT: set the 2R target and leave it.

## 2026-11-14 User strategy v2 (ifvg2.py): 50%-retracement swings (5-day legs), trend, 1h iFVG, stop ext+0.5ATR, 1.5R
- 9 coins: 665 trades, 18/mo, win 38%, -0.12R. 20 variants (stop buffer/origin, 1/2R, liquidity filter, 4h-close wait,
  no trend, BTC filter, leg/lookback/windows): all <= 0 except big legs. BTC (+0.21R) and UNI (+0.18R) positive all years.
- Big legs (ifvg2_big.py): G6 0.00R; G7 +0.19R n=79 2.2/mo, years +0.06/+0.27/+0.27, IS +0.12 OS +0.39; G8 +0.21R n=28;
  G8 at 2R -0.12R (1.5R better). Same pocket as v1. t ~1.4 after ~40 variants -> PROBATION (watch + user journal).
- Daily regime split (ifvg2_regime.py; Kaufman ER on 10/20/30 completed days + daily EMA20/50). Base: healthy trend
  -0.08..-0.14R, knife -0.07..-0.16R, chop -0.08..-0.16R, counter-trend -0.23R (20/30d). Daily EMA agrees -0.06R vs
  disagrees -0.19R. Legs>=6 ATR: no bucket consistent across windows. Regime filter does not make v2 positive. REJECT.

## 2026-11-14 User strategy: Bollinger band extreme + key level + 1h reversal (bb_lab.py, bb_v2..v4.py)
- BB13, daily EMA bias, unswept swing level, any reversal: 1531 trades, -0.09R; 19 variants all negative.
- User's NEAR chart: bias must be 4h (daily EMA lags), levels are horizontal S/R. 4h EMA50 bias + S/R (>=3 swing
  touches in 90d): BB13 -0.06R. BB length is the driver: 17 0.00 / 20 +0.05 / 21 +0.05 / 25 +0.11 / 30 -0.06R.
- 1h ENGULFING only is the edge: BB17 +0.06, BB20 +0.13 (8.4/mo, yrs +0.08/+0.18/+0.12, IS=OS), BB23 +0.13, BB25 +0.13,
  BB20 x2.5 +0.23 (3.9/mo), BB20 no level +0.11 (12.8/mo). Pin bars ~0. 6/9 coins positive (BTC +0.43, NEAR +0.27);
  LINK, HYPE negative; BNB/XRP/ZEC -0.06. ~50 variants tried. PROBATION: next = reviewer audit + book sim with Q/CRT.
- 2h-swing key levels (bb_v5.py): engulf BB20 +0.13R (4h levels) -> +0.09R (2h levels, 11.6/mo); same with stricter
  touches/tolerance; any-pattern +0.05 -> +0.03R. More levels = more trades of lower quality. REJECT; keep 4h levels.

## 2026-11-14 BB20-engulf added to the book (book_bb.py)
- Confluence rare: 13 of 301 B trades agree with a Q/CRT trade (same coin+side, 24h): +0.48R; B alone +0.11R; Q/CRT
  confirmed by B +0.24R vs +0.39R without (n=12, noise). Monthly R correlation Q+CRT vs B -0.15 (diversifies).
- Eval (rolling): safe 1.5%: Q+CRT 95% pass / median 173d / E[days] 194 -> +B x0.5 89% / 119d / 143d;
  +B x1.0 85% / 73d / 110d. Fast 3% single: 76% / 80d / 117d -> +B x0.5 75% / 60d / 85d.
## 2026-11-14 PYTH, ONDO, PENDLE (new_coins.py; 15m downloaded)
- Q +0.01R (n=40), CRT -0.06R (38), BB20-engulf -0.08R (92), iFVG big legs -0.02R (26). Per-coin samples 7-34.
  REJECT all three for now (PENDLE positive on CRT/iFVG but n 10-18).

## 2026-11-14 BB20-engulf at 4h check-ins only (bb_scan.py; user can't watch 1h)
- 7 coins (no LINK/HYPE): 1h entries +0.18R 7/mo. Entry delayed to the next check-in (skip if stop/target traded first):
  08/12/16/20/00 +0.13R (yr3 -0.07); 08/12/16/20 +0.14R (yr3 -0.02); 08/20/00 +0.10R. Median wait 2h.
- Eval 1.5%/trade (live tilts): Q+CRT 95% / 173d / E 194d; +B x0.5 81% / 137d / 182d (16% unfinished at data end).
  Flat 1.5% everything: Q+CRT 76% / 136d; +B x0.5 88% / 119d / E 143d.
- Funded 1%, 15d payouts, 1y (fixed: funded() now applies the B multiplier): Q+CRT $9.3k (worst10% $4.6k);
  +B x0.5 at 08/12/16/20 check-ins $10.6k (worst10% $7.5k, 0% blown); x0.75-1.0 adds blow-ups (29-30%).

## 2026-11-14 REVIEW: BB20-engulf audit (bb_lab.py run(bias='ema4h', key='hz', pat=('engulf',), n_bb=20))
- Code: no look-ahead found (BB/EMA50/ATR on closed setup bar i; 1h scan starts at T = open+4h; b1[n0-1] is the
  setup candle's last closed 1h bar; pivots confirmed by i-1; ext/stop use bars up to the signal close; entry
  b1[sig+1] open; stop-first, no target on fill bar, 0.04%/side, weekend skip+flat, busy, break). Independent
  re-sim matches to 1e-14. No bug fixed.
- Re-run: 9 coins n=301 8.4/mo 49% +0.127R PF 1.28 +1.06R/mo DD 11.2R, yrs +0.08/+0.18/+0.12, IS +0.13 OS +0.12,
  t=1.99. 7 picked coins +0.18R (t 2.6, post-selection); 12 coins (+BNB XRP ZEC) +0.085R t=1.53, Y1 +0.01.
  BTC carries IS (+0.66) but OS -0.03; ETH 0.00.
- Nulls (9 coins): random side -0.05 +/- 0.06 (p 0.002); random hour same side -0.02 +/- 0.07 (p 0.011); entry jittered
  -3..+4h around the engulf +0.18R (p 0.94) -> the engulf timing adds nothing; edge (if any) is the setup context.
  ~50 variants: single-test p ~0.02 does not survive deflation.
- House 4h clock (rule: hand tickets at 00/08/20 SGT): entries fire at all hours. Entering at the next scan after
  the signal (same stop, skip if stop hit while waiting): n=257 +0.08R +0.59R/mo DD 18R, yrs +0.19/+0.09/-0.02,
  IS +0.13 OS -0.02. Awake-hours (08-01 SGT) entries only: OS -0.02.
- VERDICT: REJECT for the ticket book (executable version fails OS; t~2 after ~50 variants and coin selection).
  Withdraw the book_bb.py add-on. Next (specific): 4h-clock entry at the scan right after the setup candle
  (BB20 touch + 4h EMA50 bias + hz level, no 1h pattern), stop beyond setup extreme - tests the context directly.

## 2026-11-14 BB set-and-forget limit ticket (bb_limit.py; first run had a stop-side bug -> 0 trades, fixed)
- Ticket at the 08/12/16/20 check-in after the setup candle, limit / stop beyond extreme+0.25ATR / 1.5R, valid 8h.
  4h confirm none: ~0R; 'reject' (close back inside band and below the level): -0.14..+0.04R; 'red' candle:
  limit at close +0.12R (6.9/mo) / close+0.25ATR +0.12R / wick +0.11R, but OS (since 2025-12-18) -0.02..+0.05R and
  year 3 +0.02..+0.07. Every variant fades out-of-sample. REJECT for the ticket book; ticket book stays Q + CRT.
## 2026-11-14 Forward projection (projection.py): weekly-block MC from the last 12 months / since 1 May 2026
- Last 12m: Q 5.9/mo 65% +0.57R; CRT 2.1/mo 60% +0.41R. Since May: Q 8.4/mo +0.55R; CRT 2.0/mo +0.20R.
- Combined (last 12m), flat 1.5% eval: 1 month median +1.4R (+$1.1k) [5%: -3.4R, 95%: +20R], P(loss) 31%;
  3 months median +9.8R (+$7.4k), P(+8%) 65%; 6 months median +23R (+$17k), P(loss) 6%. No position caps / guards.
## 2026-11-14 Slot rules (slots.py): first tickets to fill get the slots
- 3y: all tickets 7.4/mo 57% +0.38R +103R dd 9.9R; 2/day 54% +0.26R +55R; 2 open 53% +0.27R +58R; 3 open +0.31R +73R.
  Last 12m: all +0.52R +46R vs 2/day +0.32R +19R. Busy days (many coins firing) carry the best trades; capping by
  first-to-fill drops them. Days with 3+ fills: 25 of 160. REJECT slot caps below 3; keep all tickets with the guards.
## 2026-11-14 Setup grading by running room to next structure (room.py)
- Room = entry -> nearest untouched 4h (or daily) swing in the trade direction, in R. Q+CRT, 4h: blocked <1.5R
  +0.41R (n48) | 1.5-3R +0.25R (86) | >=3R +0.53R (68; Q alone +0.86R n19) | clear air +0.39R (78, weak yrs 1-2).
  Daily: <1.5R +0.38 | 1.5-3R +0.21 | >=3R +0.40 | clear air +0.45. Not monotonic: blocked trades still win 60%
  (breakouts run through structure). Use as an ordering label only (A+ = >=3R room on 4h), never as a skip filter.

## 2026-11-14 All 72 Bitfunded crypto perps on Q and CRT (all_coins.py, similarity.py)
- Q: all 72 +0.20R 26.6/mo (core 10 +0.43R; other 62 +0.15R, yrs -0.06/+0.20/+0.27). CRT: other 62 +0.05R, OS -0.15R.
- Q avg R per coin vs similarity (coins >= 8 trades): rank-corr with corr-to-BTC +0.47, volatility -0.35, beta 0.0,
  trend efficiency 0.0, breakout follow-through +0.22 -> coins that track BTC with moderate vol work best for Q.
- Last 12m, flat 1.5%: core uncapped 8/mo +0.53R +4.2R/mo; core capped (3 open, 3/day) +2.2R/mo; all-72 uncapped
  50/mo +0.19R +9.7R/mo but worst-5% month -26R (fails any eval); all-72 capped 22.5/mo +0.11R +2.6R/mo, worst 5% -7.7R.
- Best non-core by Q+CRT R: AVAX LTC ARB WIF JASMY SEI ENS (n 8-20 each, selection risk). Core laggards: HYPE (-3.9R), ZEC.
## 2026-11-14 Core-list swaps (core_swap.py; eval = live tilts, safe guards)
- live core 10: 7.8/mo +0.38R +2.98R/mo dd 8.9R | eval 95% med 163d E 186d.  core 8 (no HYPE/ZEC): +0.43R, dd 7.7R,
  95% / 171d / 194d. HYPE CRT -0.46R (n9); ZEC Q +0.77R (n5) / CRT +0.06R (n16).
- + rule picks (corr>=0.70 & vol<100%: AVAX DOGE ENS FLOKI LTC SUI VIRTUAL): more R/mo but dd 10-15R, pass 86-88%.
- core 8 + AVAX + LTC: 8.4/mo +0.45R +3.80R/mo dd 8.4R | 95% / 149d / E 155d (best balance; mild hindsight -
  both coins pass the rule and the results). + DOGE: 94% / 148d / 165d. Cherry-picked top 5: 95% / 149d / 159d.
- Last-12-months view (core_swap_1y.py; user wants 1y as the standard): core 10 96 trades +0.53R +4.20R/mo dd 8.0R;
  core 8 80 +0.61R +4.05 dd 5.8R; core 8 + AVAX + LTC 107 +0.55R +4.94 dd 8.4R; + rule picks (both) 154 +0.47R
  +6.08 dd 15.4R. Prior 2y all +0.31..+0.39R. Per coin only 6-15 trades in 12 months.
- HOUSE STANDARD from now: decide on the last 12 months; require the prior 2 years not negative (stability gate);
  per-coin calls need pooled evidence (rules like corr/vol), not 6-15 trades.
## 2026-11-14 User setups on all 72 coins (user_setups_all.py)
- iFVG v2 big legs (G7): all 72 last 12m n189 15.8/mo 46% +0.12R; prior 2y n460 +0.07R; core 10 +0.12R / 0.00R.
  Small but positive in both periods on a large sample (t ~1.9 pooled). WATCH: needs 1h attention (trigger is a 1h
  close) - would need alerts to be ticketable.
- BB20 limit (red, at close): all 72 +0.01R last 12m (+0.06R prior), core 10 -0.04R. REJECT.
## 2026-11-14 Swing ticket (check-in) ADOPTED into scan at half risk
- swing_checkin.py: limit placed at the next 08/12/16/20 check-in after the 1h inversion, valid 12h: all 72 last 12m
  n173 49% +0.16R, prior 2y +0.16R (instant entry +0.12 / +0.07R). Core 10 ~0R.
- book_swing.py (new core 10 Q+CRT + swing all 72): x0.5 93% pass, median 100d, E 120d (vs 95% / 149d / 155d);
  x1.0 76% / 66d. Live detector (perps.swing_setups) replayed vs backtest, 12 coins x 60 days: identical tickets
  after matching history (800 1h bars) and weekend handling.
## 2026-11-14 Swing timing (swing_timing.py, all 72, G7)
- Midline retest after the 1h inversion: 46% within 1h, 78% within 4h, 100% within 12h (median 1h).
- Instant fills before the next check-in: last 12m +0.18R (n116), prior 2y +0.03R (n276) - not consistently the best.
- Check-in ticket +0.16R / +0.16R (14.4/mo) vs instant +0.12 / +0.07R: at the check-in the limit often fills at once at
  a better price (retracement continued) or on a later retest. Zone 50% limit without the gap (2 conditions):
  +0.16R / +0.09R, 17.8/mo; zone 61.8% +0.15 / -0.00R. KEEP the 3-condition check-in ticket.
## 2026-11-14 Q / CRT slots on the new core 10 (slots_hours.py), every 4h close allowed
- Q by hour (last 12m | prior 2y): 00 +0.49|+0.17, 04 -0.38|+0.18, 08 +0.18|+0.30, 12 +0.22|-0.30, 16 +0.14(7)|-0.06,
  20 +0.51|+0.17 -> keep 00/08/20. Q by day: Mon -0.55|-0.16, Sat -0.11|-0.26, Sun +0.02|-0.17 -> skip Mon/Sat/Sun.
- CRT by hour fine (08-20); by day Fri -0.21|-0.35, Sat -1.00(4)|-0.19 -> skip Fri/Sat.
- Bot: 7-day check-ins, Q withheld outside its hours/days, CRT skip days, swing off in the tested weekend window.
## 2026-11-14 Risk 1.75% eval / 1.5% funded (risk_175.py; full book incl. swing x0.5, skip days)
- Eval: 1.5% 96% pass med 96d E 113d | 1.75% 97% / 88d / 102d | 2.0% 94% / 76d / 93d. ADOPT 1.75%.
- Funded 1y, 15d payouts: 1.0% mean $15.3k med $15.9k worst10% $9.8k blown 0% | 1.25% $16.8k / $19.4k / $5.9k / 23% |
  1.5% $15.1k / $13.7k / $1.8k / 57%. User chose 1.5% funded; data favours 1.0-1.25%.
## 2026-11-14 Money per year across the full cycle (pipeline_money.py; eval 1.75%, one account at a time, 2y chains)
- Net/yr after eval fees by funded risk: 0.75% $9.4k | 1.0% $12.5k | 1.25% $15.5k | 1.5% $17.4k (worst10% $12.3k) |
  1.75% $15.7k | 2.0% $17.4k | 2.5% $18.2k | 3.0% $19.7k (worst10% $15.0k; 1.7 funded accounts/yr, 53% of time funded).
- The user's framing holds: blowing faster and re-buying evals earns as much or more than nursing one account.
  1.5-3% all ~$17-20k/yr (differences within noise; 119 overlapping starts on 3y of data). Keep 1.5% funded.
## 2026-11-14 Bitfunded max position per coin vs account size
- Max position (instrument API maxPosition, treated as USDT notional): BTC 400k ETH 330k BNB 200k SOL 200k XRP 100k
  LTC 80k ADA 75k UNI 70k AVAX 70k LINK 50k. Full 1.75% ticket at the median stop needs ~0.45-0.9x the account size
  in notional; tight stops up to ~1.9x. 150K: BTC/ETH/SOL fit; BNB/XRP/ADA/UNI capped on tight stops; LINK/AVAX/LTC
  capped even at median stops. 100K: all fit at median except LINK; tight stops capped on ADA/UNI/LINK/AVAX/LTC.
- Bot now caps size at the coin's max position and says so ("sized by Bitfunded max position").
