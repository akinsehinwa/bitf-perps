# Research scripts

Backtests and studies behind the `bitfunded-perps` skill. They read the cache built by
`python3 perps.py data` (and the downloads in `dl_all.py`) under `trader/perps/cache/`.
Several scripts still import each other from the scratch folder they were written in;
adjust `sys.path` before re-running.

| script | what it tests |
| --- | --- |
| family.py, qlab.py | Q (4h quality breakout) family, entry/exit lab on 15m, Monte-Carlo helpers |
| crt3.py | 3-candle CRT (1h/2h/4h, LTF confirmation, key levels) |
| rq.py | Roboquant PDH/PDL sweep fade adapted to crypto |
| ema_sr.py, s2.py, strats.py | EMA x StochRSI, S/R flip, VWAP, pullbacks, RSI-2, trailing stops |
| p50bt.py | the Trading Floor P50-T2 bot replayed with its own functions |
| rs.py, fund.py, sq.py, r2.py | relative-strength rotation, funding fade, squeeze, catch-up, overnight stops, CME gap, session drift |
| daily.py, feat.py | daily-bias and per-trade feature studies |
| grid.py, wf.py, stops.py, legs.py | parameter grid / walk-forward, stop/target study, parent-leg variant |
| book2.py | multi-strategy book with per-strategy risk and the challenge simulator |
