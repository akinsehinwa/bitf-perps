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
