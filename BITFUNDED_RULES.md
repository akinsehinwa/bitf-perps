# Bitfunded 50K Two-Step Evaluation - rules as the bot uses them

Sources: [R] the rules screenshot the user shared at the start; [U] confirmed by the user in conversation;
[F] Bitfunded's public instrument feed (cb.bitfunded.com/v1/cfd/public/instruments); [A] assumption used in the
research models, NOT verified against Bitfunded's site (bitfunded.com is blocked from the bot's cloud session).
Last reviewed 2026-11-21.

## Account

| Item | Value | Source |
|---|---|---|
| Program | Two Steps Evaluation, Advanced, 50,000 USDT | [R] |
| Price | $399 | [R] |
| Instruments | USDT perpetuals (crypto, plus some TradFi perps like gold, oil, stocks) | [R][F] |
| Prices | Binance perp prices | [U] |

## Targets and loss limits

| | Stage 1 | Stage 2 | Funded |
|---|---|---|---|
| Profit target | **+8%** ($4,000) | **+5%** ($2,500) | none |
| Max daily loss | **5%** ($2,500) | **5%** ($2,500) | **5%** ($2,500) |
| Max total loss | **10%** ($5,000; floor $45,000) | **8%** ($4,000; floor $46,000) | **8%** ($4,000) |

- Daily loss resets at **00:00 UTC+8 (Singapore time)**, settling 00:00-00:10. [R]
- Loss limits count **floating (open) P&L**, not only closed trades. [R]
- Max total loss is treated as a **static floor** from the starting balance. [A - confirm whether it trails]
- Targets count **realized** profit (positions closed). [A]

## Trading rules

| Rule | Value | Source |
|---|---|---|
| Leverage | up to **1:5** | [R] |
| Fees | **0.04% of position size per side** (open and close); no funding or holding cost | [U] |
| Max open positions | **5** | [R] |
| Total margin | must stay **under 65%** of the account | [R] |
| Max hold per position | **10 days** for majors (BTC ETH BNB XRP SOL TRX HYPE ZEC DOGE ADA), **7 days** for others | [R] |
| Minimum activity | **2 closed trades per stage**, each held **10+ minutes** | [R] |
| Stop-loss / take-profit | expected on every trade | [R] |
| Hedging | not allowed (no opposite positions in the same coin) | [R] |
| Max position size per coin | fixed **USDT notional** cap per coin, the same on 50K and 100K accounts; e.g. BTC $400k, ETH $330k, BNB/SOL $200k, XRP $100k, LTC $80k, ADA $75k, UNI/AVAX $70k, LINK $50k, ORDI $30k. At 5x the order panel shows it as margin (cap / 5) | [F][U] |
| Time limit per stage | none known | [A] |
| Weekend holding | allowed (positions run through weekends with SL/TP live) | [U] |

## Funded account and payouts

| Item | Value used in models | Source |
|---|---|---|
| Profit split | **80%** to the trader | [A] |
| Payout frequency | every **15 days** | [A] |
| Fee refund | $399 refunded with the **3rd payout** | [A] |
| After a payout | balance returns to the starting size; loss floor unchanged | [A] |

## How the bot stays inside the rules (stricter than the firm)

- Risk per trade: **1.75%** in the eval, **1.5%** funded (halved while BTC's 7-day volatility is contracting;
  swing tickets at half again).
- Daily guard **4.25%** (firm 5%): all open stops + today's realized loss can never exceed it.
- **1.0% buffer** above the max-loss floor.
- Max **3** open positions (firm 5), open risk under **4.5%**, margin under **60%** total and **30%** per position.
- One position per coin, never hedged; sizes capped at each coin's max position.
- Risk halves while the stage is down more than 3%.
- Time stops (Q 48h, CRT 24h, swing 96h) keep every trade well inside the 7/10-day hold limit.
