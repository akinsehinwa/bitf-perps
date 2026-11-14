#!/usr/bin/env python3
"""bitfunded-perps: signals, position sizing, a rule guard, a trade journal and a
challenge backtest for a Bitfunded 2-step evaluation traded on Binance USDT-M
perpetuals.

Nothing in here places an order. Bitfunded has no order API; you place every
order yourself on the Bitfunded platform, with the stop-loss and take-profit
this tool prints.

Commands
  rules                     the stage rules and every limit this tool enforces
  scan [--symbols A,B]      live setups on closed 1h bars (Binance spot mirror)
  plan SYMBOL long|short --entry P --stop P [--target P]
                            size a trade to the risk budget, print the ticket
  open  (--signal N | SYMBOL SIDE --entry P --stop P --target P --qty Q)
  close ID --exit P [--fees F]
  status                    stage progress, daily-loss and max-loss headroom
  stage N | funded          start the next stage (fresh 50,000 balance)
  tune                      adjust the risk multiplier from your journal
  data [--months N]         download Binance perp 1h history (public archive)
  backtest [--risk 1.0] [--every 2] [--split 0.67]
                            replay the strategy and simulate challenges
State lives in ./trader/perps/ (override with PERPS_DIR).
"""
import argparse, csv, datetime as dt, io, json, math, os, statistics, sys, time
import urllib.request, urllib.error, zipfile

UTC = dt.timezone.utc
HOUR_MS = 3600_000
DAY_MS = 86_400_000
STATE = os.environ.get("PERPS_DIR") or os.path.join(os.getcwd(), "trader", "perps")
UA = "bitfunded-perps/1.0"

MAJORS = ["BTC", "ETH", "BNB", "XRP", "SOL", "TRX", "HYPE", "ZEC", "DOGE", "ADA"]  # Bitfunded's 10-day-hold list
WATCHLIST = ["BTC", "ETH", "BNB", "XRP", "SOL", "ADA", "UNI", "LINK", "AVAX", "LTC"]   # 2026-11-14: HYPE/ZEC out, AVAX/LTC in

DEFAULT_CONFIG = {
    "account_size": 50000,
    "program": "Bitfunded Two Steps Evaluation, Advanced 50,000 USDT ($399)",
    "stages": {
        "1": {"profit_target_pct": 8, "max_daily_loss_pct": 5, "max_loss_pct": 10},
        "2": {"profit_target_pct": 5, "max_daily_loss_pct": 5, "max_loss_pct": 8},
        "funded": {"profit_target_pct": None, "max_daily_loss_pct": 5, "max_loss_pct": 8},
    },
    "firm": {
        "max_leverage": 5,
        "fee_pct_per_side": 0.04,
        "funding": "none (trader confirms only the 0.04% open and close fee is charged)",
        "holding_cost": "none",
        "cost_model": "fee_only",
        "daily_reset": "00:00 UTC+8 (settles 00:00-00:10)",
        "daily_reset_utc_offset_hours": 8,
        "max_open_positions": 5,
        "max_margin_pct": 65,
        "max_hold_days_major": 10,
        "max_hold_days_minor": 7,
        "major_assets": MAJORS,
        "min_closed_trades_per_stage": 2,
        "min_hold_minutes": 10,
    },
    "symbols": WATCHLIST,
    "schedule": {
        "tz": "Asia/Singapore (UTC+8), same clock as Bitfunded's daily reset",
        "tz_offset_hours": 8,
        "scan_hours": [8, 20, 0],
        "skip_days": ["Mon", "Sat", "Sun"],          # Q only (2026-11-14 slot study: Mon/Sat/Sun negative in both periods)
        "weekend_stop": "Sat 04:00",
        "weekend_resume": "Sun 20:00",
        "flat_for_weekend": False,
        "weekend_pause": False,
        "checkins": [8, 12, 16, 20, 0],
        "max_trades_per_day": 3,
    },
    "strategy": {
        "interval": "4h",
        "be_at_r": 0,
        "setups": ["breakout"],
        "regime_filter": True,
        "min_body_atr": 1.0,
        "aplus_breadth": 3,
        "crt": {"enabled": True, "hours": [8, 12, 16, 20], "body": 0.7, "min_range_atr": 1.0,
                "min_rr": 1.0, "buf_atr": 0.1, "btc_daily_filter": True, "slippage_pct": 0.05, "hold_hours": 24,
                "skip_days": ["Fri", "Sat"]},
        "swing": {"enabled": True, "symbols": "all", "hours": [8, 12, 16, 20], "risk_mult": 0.5,
                  "min_leg_atr": 7.0, "pivot_leg_atr": 2.0, "leg_lookback_h": 120, "window_h": 48,
                  "valid_h": 12, "invalidate": 0.786, "stop_buf_atr": 0.5, "hold_hours": 96},
        "fill_pen_atr": 0.05,
        "donchian": 55,
        "ema_fast": 50,
        "ema_slow": 200,
        "atr": 14,
        "atr_stop": 2.0,
        "target_r": 1.5,
        "rsi": 14,
        "rsi_pull": 40,
        "max_hold_bars": 12,
        "entry": "limit",
        "limit_atr": 0.5,
        "limit_valid_hours": 8,
        "exec_interval": "1h",
        "slippage_pct_per_side": 0.0,
    },
    "risk": {
        "stage1_risk_pct": 1.75,
        "stage2_risk_pct": 1.75,
        "vol_tilt": {"enabled": True, "lookback_bars": 42, "contracting_mult": 0.5},
        "setup_risk_mult": {"crt4h": 0.75},
        "funded_risk_pct": 1.5,
        "min_risk_pct": 0.25,
        "max_risk_pct": 2.5,
        "risk_mult": 1.0,
        "daily_guard_pct": 4.25,
        "max_loss_buffer_pct": 1.0,
        "max_open_positions": 3,
        "max_open_risk_pct": 4.5,
        "max_margin_pct": 60,
        "max_position_margin_pct": 30,
        "drawdown_cut_pct": 3.0,
        "drawdown_cut_mult": 0.5,
        "finish_line": False,
        "min_stop_pct": 0.4,
    },
}


# ---------------------------------------------------------------- state / io

def path(*p):
    return os.path.join(STATE, *p)


def load_json(p, default):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, p)


def merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_config():
    p = path("config.json")
    user = load_json(p, None)
    if user is None:
        save_json(p, DEFAULT_CONFIG)
        user = {}
    return merge(DEFAULT_CONFIG, user)


def load_journal():
    return load_json(path("journal.json"), {"stage": "1", "stage_started": now_iso(), "trades": [], "history": []})


def save_journal(j):
    save_json(path("journal.json"), j)


def now_utc():
    return dt.datetime.now(UTC)


def now_iso():
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def day_key(t_ms, offset_h=8):
    """Bitfunded's trading day: resets at 00:00 UTC+8."""
    return (t_ms + offset_h * HOUR_MS) // DAY_MS


IV_MS = {"1h": HOUR_MS, "4h": 4 * HOUR_MS, "1d": DAY_MS}
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def local_dt(ms, off):
    return dt.datetime.fromtimestamp(ms / 1000 + off * 3600, UTC).replace(tzinfo=None)


def _wm(spec):
    d, hm = spec.split()
    h, m = hm.split(":")
    return WD.index(d) * 1440 + int(h) * 60 + int(m)


def in_weekend(ms, sch):
    if not sch.get("weekend_pause", True):
        return False                           # 2026-11-14: user trades 7 days a week, same check-ins
    d = local_dt(ms, sch["tz_offset_hours"])
    wm = d.weekday() * 1440 + d.hour * 60 + d.minute
    a, b = _wm(sch["weekend_stop"]), _wm(sch["weekend_resume"])
    return a <= wm < b if a < b else (wm >= a or wm < b)


def in_tested_weekend(ms, sch):
    """The Sat 04:00 - Sun 20:00 SGT window that every backtest excluded (used even with weekend_pause off)."""
    d = local_dt(ms, sch["tz_offset_hours"])
    wm = d.weekday() * 1440 + d.hour * 60 + d.minute
    a, b = _wm(sch["weekend_stop"]), _wm(sch["weekend_resume"])
    return a <= wm < b if a < b else (wm >= a or wm < b)


def entry_allowed(close_ms, sch):
    """A new trade may start at this bar close: a scheduled scan hour, not the weekend."""
    d = local_dt(close_ms, sch["tz_offset_hours"])
    if WD[d.weekday()] in sch.get("skip_days", []):
        return False
    return d.hour in sch["scan_hours"] and not in_weekend(close_ms, sch)


def next_weekend_stop(ms, sch):
    off = sch["tz_offset_hours"]
    d = local_dt(ms, off)
    wd, hm = sch["weekend_stop"].split()
    h, m = map(int, hm.split(":"))
    cand = d.replace(hour=h, minute=m, second=0, microsecond=0) + dt.timedelta(days=(WD.index(wd) - d.weekday()) % 7)
    if cand <= d:
        cand += dt.timedelta(days=7)
    return int((cand.replace(tzinfo=UTC).timestamp() - off * 3600) * 1000)


def next_scans(sch, n=6, from_ms=None):
    off = sch["tz_offset_hours"]
    t = (from_ms or int(now_utc().timestamp() * 1000)) // HOUR_MS * HOUR_MS + HOUR_MS
    out = []
    while len(out) < n:
        if entry_allowed(t, sch):
            out.append(t)
        t += HOUR_MS
    return out


def fetch(url, tries=3):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if k == tries - 1:
                raise
        except (urllib.error.URLError, OSError):
            if k == tries - 1:
                raise
        time.sleep(2 * (k + 1))


def money(x):
    return ("-$" if x < 0 else "$") + format(abs(x), ",.2f")


def fmt_px(x):
    if x >= 1000:
        return "%.1f" % x
    if x >= 10:
        return "%.2f" % x
    if x >= 1:
        return "%.4f" % x
    return "%.5f" % x


# ---------------------------------------------------------------- indicators

def ema(xs, n):
    out = [None] * len(xs)
    k = 2 / (n + 1)
    s = None
    for i, x in enumerate(xs):
        if i < n - 1:
            continue
        s = sum(xs[i - n + 1:i + 1]) / n if s is None else x * k + s * (1 - k)
        out[i] = s
    return out


def atr(h, l, c, n):
    out = [None] * len(c)
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    s = None
    for i in range(len(c)):
        if i == n - 1:
            s = sum(tr[:n]) / n
        elif i >= n:
            s = (s * (n - 1) + tr[i]) / n
        if i >= n - 1:
            out[i] = s
    return out


def rsi(c, n):
    out = [None] * len(c)
    g = lo = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        up, dn = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            g += up
            lo += dn
            if i < n:
                continue
            g /= n
            lo /= n
        else:
            g = (g * (n - 1) + up) / n
            lo = (lo * (n - 1) + dn) / n
        out[i] = 100.0 if lo == 0 else 100 - 100 / (1 + g / lo)
    return out


def channel(h, l, n):
    hh, ll = [None] * len(h), [None] * len(l)
    for i in range(n, len(h)):
        hh[i] = max(h[i - n:i])
        ll[i] = min(l[i - n:i])
    return hh, ll


def indicators(bars, st):
    o = [b[1] for b in bars]; h = [b[2] for b in bars]; l = [b[3] for b in bars]; c = [b[4] for b in bars]
    hh, ll = channel(h, l, st["donchian"])
    return {"t": [b[0] for b in bars], "o": o, "h": h, "l": l, "c": c,
            "ef": ema(c, st["ema_fast"]), "es": ema(c, st["ema_slow"]),
            "atr": atr(h, l, c, st["atr"]), "rsi": rsi(c, st["rsi"]), "hh": hh, "ll": ll}


def signal(ind, i, st):
    """Setup on the CLOSED bar i, or None. Long and short."""
    if i < 1:
        return None
    c, ef, es, a = ind["c"][i], ind["ef"][i], ind["es"][i], ind["atr"][i]
    if ef is None or es is None or a is None or ind["hh"][i - 1] is None or ind["rsi"][i - 1] is None:
        return None
    setups = st["setups"]
    if st.get("min_body_atr") and abs(c - ind["o"][i]) < st["min_body_atr"] * a:
        return None                     # weak breakout candle: body under min_body_atr x ATR
    up, dn = ef > es, ef < es
    stop_d = st["atr_stop"] * a
    if "breakout" in setups:
        if up and c > ind["hh"][i] and ind["c"][i - 1] <= ind["hh"][i - 1]:
            return {"setup": "breakout", "side": "long", "stop_d": stop_d}
        if dn and c < ind["ll"][i] and ind["c"][i - 1] >= ind["ll"][i - 1]:
            return {"setup": "breakout", "side": "short", "stop_d": stop_d}
    if "pullback" in setups:
        p = st["rsi_pull"]
        r0, r1 = ind["rsi"][i - 1], ind["rsi"][i]
        if up and c > es and r0 < p <= r1:
            return {"setup": "pullback", "side": "long", "stop_d": stop_d}
        if dn and c < es and r0 > 100 - p >= r1:
            return {"setup": "pullback", "side": "short", "stop_d": stop_d}
    return None


# ---------------------------------------------------------------- risk engine

def stage_rules(cfg, stage):
    return cfg["stages"][str(stage)]


def risk_budget(cfg, stage, realized, realized_today, open_risk, open_notional, n_open, target_r=None, mult=1.0, mult_why=""):
    """Dollars to risk on the next trade, and the limit that decided it.
    The invariant: realized loss today + every open position's loss at its stop
    (fees included) never exceeds our daily guard, and the same for the overall
    max-loss floor. With stops on every trade, the firm's limits (which count
    floating loss) can only be breached by slippage beyond the guard buffer."""
    acct = cfg["account_size"]
    R = cfg["risk"]
    rules = stage_rules(cfg, stage)
    max_open = min(R["max_open_positions"], cfg["firm"]["max_open_positions"])
    if n_open >= max_open:
        return 0.0, "max %d open positions" % max_open
    key = "stage%s_risk_pct" % stage if str(stage) in ("1", "2") else "funded_risk_pct"
    pct = R[key] * R.get("risk_mult", 1.0)
    why = "base %.2f%% (stage %s) x mult %.2f" % (R[key], stage, R.get("risk_mult", 1.0))
    if mult != 1.0:
        pct *= mult
        why += " x %.2f (%s)" % (mult, mult_why or "setup/regime")
    if realized < -R["drawdown_cut_pct"] / 100 * acct:
        pct *= R["drawdown_cut_mult"]
        why += ", halved: down more than %.1f%%" % R["drawdown_cut_pct"]
    tgt = rules.get("profit_target_pct")
    if tgt and R["finish_line"]:
        remaining = tgt / 100 * acct - realized
        tr = target_r or cfg["strategy"]["target_r"]
        need_pct = remaining / tr / acct * 100 * 1.15  # 15% cushion for fees
        if need_pct < pct:
            pct = max(R["min_risk_pct"], need_pct)
            why += ", finish line: %s left to target" % money(remaining)
    pct = max(R["min_risk_pct"], min(R["max_risk_pct"], pct))
    risk = pct / 100 * acct
    rooms = {
        "daily guard %.1f%%" % R["daily_guard_pct"]: R["daily_guard_pct"] / 100 * acct - max(0.0, -realized_today) - open_risk,
        "max-loss floor (%.1f%% firm - %.1f%% buffer)" % (rules["max_loss_pct"], R["max_loss_buffer_pct"]):
            (rules["max_loss_pct"] - R["max_loss_buffer_pct"]) / 100 * acct + realized - open_risk,
        "open-risk cap %.1f%%" % R["max_open_risk_pct"]: R["max_open_risk_pct"] / 100 * acct - open_risk,
    }
    for name, room in rooms.items():
        if room < risk:
            risk = room
            why = "capped by " + name
    if risk < 0.5 * R["min_risk_pct"] / 100 * acct:
        return 0.0, "no room: " + why
    return risk, why


def size_trade(cfg, entry, stop, risk_usd, open_notional, fee=None, side=None, max_pos=None):
    """Quantity so a stop-out (fees, spread and slippage included) loses risk_usd."""
    acct = cfg["account_size"]
    R, F, S = cfg["risk"], cfg["firm"], cfg["strategy"]
    lev = F["max_leverage"]
    stop_frac = abs(entry - stop) / entry
    fee = F["fee_pct_per_side"] / 100 if fee is None else fee
    side = S["slippage_pct_per_side"] / 100 if side is None else side
    cost = 2 * (fee + side)
    notional = risk_usd / (stop_frac + cost)
    caps = {"risk": notional,
            "per-position margin %d%%" % R["max_position_margin_pct"]: R["max_position_margin_pct"] / 100 * acct * lev,
            "total margin %d%%" % R["max_margin_pct"]: max(0.0, R["max_margin_pct"] / 100 * acct * lev - open_notional)}
    if max_pos:
        caps["Bitfunded max position $%s" % format(int(max_pos), ",")] = max_pos   # USDT notional (confirmed by the user 2026-11-14)
    limit = min(caps, key=caps.get)
    notional = caps[limit]
    qty = notional / entry
    loss_at_stop = notional * (stop_frac + cost)
    return {"qty": qty, "notional": notional, "margin": notional / lev, "leverage": lev,
            "limit": limit, "loss_at_stop": loss_at_stop, "stop_pct": stop_frac * 100,
            "fees_round_trip": notional * 2 * fee}


# ---------------------------------------------------------------- journal math

def journal_state(cfg, j, now_ms=None):
    now_ms = now_ms or int(now_utc().timestamp() * 1000)
    off = cfg["firm"]["daily_reset_utc_offset_hours"]
    today = day_key(now_ms, off)
    realized = realized_today = 0.0
    open_risk = open_notional = 0.0
    opens, closed = [], 0
    for t in j["trades"]:
        if t.get("closed_at"):
            closed += 1
            realized += t["pnl"]
            if day_key(int(parse_iso(t["closed_at"]).timestamp() * 1000), off) == today:
                realized_today += t["pnl"]
        else:
            opens.append(t)
            open_risk += t["risk_usd"]
            open_notional += t["notional"]
    return {"realized": realized, "realized_today": realized_today, "open_risk": open_risk,
            "open_notional": open_notional, "open": opens, "closed": closed}


# ---------------------------------------------------------------- live data

FEED_IV = {"1h": ("1h", "60", "1H"), "4h": ("4h", "240", "4H"), "1d": ("1d", "D", "1Dutc")}


def _closed(rows, iv_ms):
    now_ms = int(now_utc().timestamp() * 1000)
    rows = sorted({r[0]: r for r in rows}.values())
    return [r for r in rows if r[0] + iv_ms <= now_ms]


def live_klines(sym, interval="4h", need=320):
    """Closed perp candles with fallbacks, like the user's Trading Floor engine: Binance USDT-M futures,
    then Bybit linear, then OKX USDT swaps; Binance SPOT only as a last resort. Returns (bars, source)."""
    b_iv, by_iv, okx_iv = FEED_IV[interval]
    iv_ms = IV_MS[interval]
    pair = sym + "USDT"
    try:
        raw = fetch("https://fapi.binance.com/fapi/v1/klines?symbol=%s&interval=%s&limit=%d" % (pair, b_iv, min(need, 1500)), tries=1)
        rows = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in json.loads(raw)]
        if len(rows) >= need - 5:
            return _closed(rows, iv_ms), "binance-perp"
    except Exception:
        pass
    try:
        raw = fetch("https://api.bybit.com/v5/market/kline?category=linear&symbol=%s&interval=%s&limit=%d" % (pair, by_iv, min(need, 1000)), tries=1)
        lst = json.loads(raw)["result"]["list"]
        rows = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in lst]
        if len(rows) >= need - 5:
            return _closed(rows, iv_ms), "bybit-perp"
    except Exception:
        pass
    try:
        inst = "%s-USDT-SWAP" % sym
        rows, after = [], ""
        for _ in range(need // 100 + 1):
            url = "https://www.okx.com/api/v5/market/history-candles?instId=%s&bar=%s&limit=100%s" % (inst, okx_iv, after)
            data = json.loads(fetch(url, tries=1))["data"]
            if not data:
                break
            rows += [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data if k[8] == "1"]
            after = "&after=%s" % data[-1][0]
            if len(rows) >= need:
                break
        if len(rows) >= need - 5:
            return _closed(rows, iv_ms), "okx-perp"
    except Exception:
        pass
    return spot_klines(sym, interval), "binance-SPOT (fallback)"


def is_stale(bars, interval, grace_min=20):
    """The latest closed candle must be the one that just closed (within grace minutes)."""
    if not bars:
        return True
    now_ms = int(now_utc().timestamp() * 1000)
    return bars[-1][0] + IV_MS[interval] < now_ms - IV_MS[interval] - grace_min * 60_000


def spot_klines(sym, interval="1h", limit=1000):
    url = "https://data-api.binance.vision/api/v3/klines?symbol=%sUSDT&interval=%s&limit=%d" % (sym, interval, limit)
    raw = fetch(url)
    if not raw:
        return []
    now_ms = int(now_utc().timestamp() * 1000)
    return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])]
            for k in json.loads(raw) if int(k[6]) < now_ms]  # closed bars only


# ---------------------------------------------------------------- Bitfunded markets

MARKETS_URL = "https://cb.bitfunded.com/v1/cfd/public/instruments?quote=all"


def fetch_markets():
    """Bitfunded's own instrument list (public endpoint behind bitfunded.com/markets)."""
    raw = json.loads(fetch(MARKETS_URL))["data"]
    out = {}
    for i in raw:
        if i.get("status") != "online":
            continue
        name = i["symbol"].upper().replace("USDT", "")
        out[name] = {"type": "TradFi" if i.get("sectors") else "crypto", "fullName": i.get("fullName"),
                     "taker_fee": i["takerFee"], "maker_fee": i["makerFee"],
                     "spread_open": i["openSpread"], "spread_close": i["closeSpread"],
                     "settlement_rate": i["settlementRate"], "settlement_hours": i["fundingIntervalHours"],
                     "max_position": i.get("oneMaxPosition"), "binance": None,
                     "lot": i.get("oneLotSize"), "min_lots": i.get("minSize"), "price_dp": i.get("pricePrecision")}
    return out


def load_markets():
    return load_json(path("markets.json"), None) or load_json(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "markets.default.json"), {})


def binance_symbol(name, markets=None):
    m = (markets or load_markets()).get(name, {})
    return m.get("binance") or name


def resolve_binance(name):
    for b in (name, "1000" + name, "1000000" + name):
        if fetch(ARCHIVE % ("monthly", b, "4h", b, "4h", "2026-10")) is not None:
            return b
    return None


def symbol_costs(cfg, name, markets=None):
    """Per-side cost fractions and holding cost per hour for one instrument."""
    m = (markets or load_markets()).get(name)
    fee = cfg["firm"]["fee_pct_per_side"] / 100
    slip = cfg["strategy"]["slippage_pct_per_side"] / 100
    # The trader's experience on the platform: 0.04% on open and on close, nothing else.
    # The API's spread / settlement fields are ignored unless cost_model is "api".
    if not m or cfg["firm"].get("cost_model", "fee_only") == "fee_only":
        return {"fee": fee, "side": slip, "hold_per_hour": 0.0}
    hold = m["settlement_rate"] / m["settlement_hours"] if cfg["firm"].get("holding_cost") == "settlement" else 0.0
    return {"fee": max(fee, m["taker_fee"]), "side": slip + (m["spread_open"] + m["spread_close"]) / 2,
            "hold_per_hour": hold}


# ---------------------------------------------------------------- archive data

ARCHIVE = "https://data.binance.vision/data/futures/um/%s/klines/%sUSDT/%s/%sUSDT-%s-%s.zip"


def parse_zip(blob):
    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in z.namelist():
            for r in csv.reader(io.TextIOWrapper(z.open(name), "utf-8")):
                if not r or not r[0].strip().isdigit():
                    continue  # header row
                t = int(r[0])
                if t > 10 ** 14:
                    t //= 1000
                rows.append([t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
    return rows


def cache_file(sym, iv):
    return path("cache", "%s-%s.json" % (sym, iv))


def download(name, iv, months):
    sym = binance_symbol(name).replace("USDT", "")
    have = {b[0]: b for b in load_json(cache_file(name, iv), [])}
    today = now_utc().date()
    first = today.replace(day=1)
    got = 0
    for m in range(months, 0, -1):
        y, mo = first.year, first.month - m
        while mo <= 0:
            y, mo = y - 1, mo + 12
        tag = "%04d-%02d" % (y, mo)
        start = int(dt.datetime(y, mo, 1, tzinfo=UTC).timestamp() * 1000)
        if start in have and start + 27 * DAY_MS in have:
            continue
        blob = fetch(ARCHIVE % ("monthly", sym, iv, sym, iv, tag))
        if blob:
            for b in parse_zip(blob):
                have[b[0]] = b
            got += 1
    d = first
    while d < today:  # this month, day by day
        tag = d.isoformat()
        start = int(dt.datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)
        if start not in have:
            blob = fetch(ARCHIVE % ("daily", sym, iv, sym, iv, tag))
            if blob:
                for b in parse_zip(blob):
                    have[b[0]] = b
                got += 1
        d += dt.timedelta(days=1)
    bars = sorted(have.values())
    save_json(cache_file(name, iv), bars)
    return bars, got


# ---------------------------------------------------------------- backtest

def btc_vol_state(bars, n=42):
    """BTC 7-day realized volatility state by 4h bar open time: True = expanding (stdev of the last n closed
    4h log returns above the n before), False = contracting. Research: Q +0.44/+0.65R expanding vs
    +0.25/+0.26R contracting (first 2 years / last year); sizing Q 2% / 1% kept the pass rate highest."""
    c = [b[4] for b in bars]
    lr = [0.0] + [math.log(c[i] / c[i - 1]) for i in range(1, len(c))]
    out = {}
    for i in range(2 * n, len(c)):
        out[bars[i][0]] = statistics.pstdev(lr[i - n + 1:i + 1]) > statistics.pstdev(lr[i - 2 * n + 1:i - n + 1])
    return out


def vol_mult(cfg, expanding):
    vt = cfg["risk"].get("vol_tilt", {})
    if not vt.get("enabled") or expanding is None or expanding:
        return 1.0
    return vt.get("contracting_mult", 0.5)


def btc_regime(bars, st):
    """BTC 4h trend by bar open time: +1 when EMA fast > EMA slow, -1 below."""
    c = [b[4] for b in bars]
    ef, es = ema(c, st["ema_fast"]), ema(c, st["ema_slow"])
    return {b[0]: (1 if ef[i] > es[i] else -1) for i, b in enumerate(bars) if ef[i] is not None and es[i] is not None}


def gen_trades(sym, bars, st, sch=None, costs=None, regime=None):
    """Every trade the rules take on one symbol, one at a time, sized later.
    A signal counts only on a bar that closes at a scheduled scan hour outside
    the weekend. Entry at the next bar's open; stop and target fixed from the
    signal bar's ATR; a bar that touches both is a stop (worst case); optional
    breakeven stop once price has gone be_at_r in favour; time exit after
    max_hold_bars; closed at the weekend stop when flat_for_weekend."""
    ind = indicators(bars, st)
    iv = IV_MS[st["interval"]]
    n = len(bars)
    slip = costs["side"] if costs else st["slippage_pct_per_side"] / 100
    fee = costs["fee"] if costs else None
    hold_h = costs["hold_per_hour"] if costs else 0.0
    be = st.get("be_at_r") or 0
    o, h, l, c, t = ind["o"], ind["h"], ind["l"], ind["c"], ind["t"]
    out, i = [], st["ema_slow"] + 1
    while i < n - 1:
        if sch and not entry_allowed(t[i] + iv, sch):
            i += 1
            continue
        sig = signal(ind, i, st)
        if sig and regime is not None and st.get("regime_filter"):
            r = regime.get(t[i])
            if r is None or (r > 0) != (sig["side"] == "long"):
                sig = None
        if not sig:
            i += 1
            continue
        j = i + 1
        side = 1 if sig["side"] == "long" else -1
        e0, d = o[j], sig["stop_d"]
        entry = e0 * (1 + side * slip)
        stop, target = e0 - side * d, e0 + side * st["target_r"] * d
        flat_ms = next_weekend_stop(t[j], sch) if sch and sch.get("flat_for_weekend") else None
        px, k, why = None, j, "time"
        for k in range(j, min(n, j + st["max_hold_bars"])):
            if flat_ms is not None and t[k] >= flat_ms:
                px, why = o[k] * (1 - side * slip), "weekend"
                break
            if side == 1:
                if l[k] <= stop:
                    px, why = min(o[k], stop) * (1 - slip), "stop" if stop < e0 else "breakeven"
                elif h[k] >= target:
                    px, why = max(o[k], target) if k > j else target, "target"
                elif be and h[k] >= e0 + be * d:
                    stop = max(stop, e0 * 1.0015)
            else:
                if h[k] >= stop:
                    px, why = max(o[k], stop) * (1 + slip), "stop" if stop > e0 else "breakeven"
                elif l[k] <= target:
                    px, why = min(o[k], target) if k > j else target, "target"
                elif be and l[k] <= e0 - be * d:
                    stop = min(stop, e0 * 0.9985)
            if px is not None:
                break
        if px is None:
            px = c[k] * (1 - side * slip)
        t_out = t[k] + (0 if why == "weekend" else iv)
        rec = {"sym": sym, "setup": sig["setup"], "side": sig["side"], "t_in": t[j], "t_out": t_out,
               "ret": side * (px - entry) / entry - hold_h * (t_out - t[j]) / HOUR_MS,
               "stop_frac": d / e0, "exit": why, "cost_side": slip}
        if fee is not None:
            rec["fee"] = fee
        out.append(rec)
        i = k + 1 if why != "weekend" else k
    return out


def gen_trades_exec(sym, bars4, bars1, st, sch=None, costs=None, regime=None, gate=None):
    """4h signal, 1h execution: limit at signal close -/+ limit_atr x ATR, valid
    limit_valid_hours; stop at signal close -/+ atr_stop x ATR (same price as a
    market entry would use, so the risk is smaller); target target_r x risk from
    the fill. Exits walk 1h bars (stop first if one bar touches both), time stop
    max_hold_bars x 4h, closed at the weekend stop."""
    iv4 = IV_MS[st["interval"]]
    ind = indicators(bars4, st)
    idx = {b[0]: n for n, b in enumerate(bars1)}
    slip = costs["side"] if costs else st["slippage_pct_per_side"] / 100
    hold = st["max_hold_bars"] * iv4 // HOUR_MS
    out, busy = [], 0
    for i in range(st["ema_slow"] + 1, len(bars4) - 1):
        close_ms = ind["t"][i] + iv4
        if close_ms < busy or (sch and not entry_allowed(close_ms, sch)):
            continue
        sig = signal(ind, i, st)
        if not sig:
            continue
        if regime is not None and st.get("regime_filter"):
            r = regime.get(ind["t"][i])
            if r is None or (r > 0) != (sig["side"] == "long"):
                continue
        if gate is not None and not gate(sym, close_ms, sig["side"], i, ind, bars4):
            continue                      # research hook: cross-coin filters (relative strength, volume)
        n0 = idx.get(close_ms)
        if n0 is None:
            continue
        s = 1 if sig["side"] == "long" else -1
        c, a = ind["c"][i], ind["atr"][i]
        stop = c - s * st["atr_stop"] * a
        if st.get("entry", "market") == "limit":
            lim = c - s * st["limit_atr"] * a
            n = None
            for m in range(n0, min(len(bars1), n0 + st["limit_valid_hours"])):
                pen = st.get("fill_pen_atr", 0.0) * a      # price must trade THROUGH the limit
                if (s == 1 and bars1[m][3] <= lim - pen) or (s == -1 and bars1[m][2] >= lim + pen):
                    n, e = m, (min(bars1[m][1], lim) if s == 1 else max(bars1[m][1], lim))
                    break
            if n is None:
                continue
        else:
            n, e = n0, bars1[n0][1] * (1 + s * slip)
        d = abs(e - stop)
        if (s == 1 and stop >= e) or (s == -1 and stop <= e):
            continue
        fee_rt = 2 * (costs["fee"] if costs else 0.0004)
        tgt = e + s * (st["target_r"] * (d + fee_rt * e) + fee_rt * e)   # after-fee target, as the live ticket
        flat = next_weekend_stop(bars1[n][0], sch) if sch and sch.get("flat_for_weekend") else None
        px, why, m = None, "time", n
        for m in range(n, min(len(bars1), n + hold)):
            o, h, l = bars1[m][1], bars1[m][2], bars1[m][3]
            if flat is not None and bars1[m][0] >= flat:
                px, why = o * (1 - s * slip), "weekend"
                break
            if (s == 1 and l <= stop) or (s == -1 and h >= stop):
                px = (min(o, stop) if s == 1 else max(o, stop)) if m > n else stop
                px, why = px * (1 - s * slip), "stop"
                break
            if m > n and ((s == 1 and h >= tgt) or (s == -1 and l <= tgt)):
                px, why = tgt, "target"      # never on the fill bar: order inside the bar is unknown
                break
        if px is None:
            px = bars1[m][4] * (1 - s * slip)
        t_out = bars1[m][0] + (0 if why == "weekend" else HOUR_MS)
        rec = {"sym": sym, "setup": sig["setup"], "side": sig["side"], "t_in": bars1[n][0], "t_out": t_out, "sig_t": ind["t"][i],
               "ret": s * (px - e) / e, "stop_frac": d / e, "exit": why, "cost_side": slip}
        if costs:
            rec["fee"] = costs["fee"]
        out.append(rec)
        busy = t_out
    return out


def trade_r(tr, fee_frac, slip_frac):
    fee_frac = tr.get("fee", fee_frac)
    slip_frac = tr.get("cost_side", slip_frac)
    cost = 2 * (fee_frac + slip_frac)
    return (tr["ret"] - 2 * fee_frac) / (tr["stop_frac"] + cost)


def stats(trades, cfg):
    if not trades:
        return "no trades"
    fee = cfg["firm"]["fee_pct_per_side"] / 100
    slip = cfg["strategy"]["slippage_pct_per_side"] / 100
    rs = [trade_r(t, fee, slip) for t in trades]
    wins = [r for r in rs if r > 0]
    gross_w = sum(wins)
    gross_l = -sum(r for r in rs if r <= 0)
    pf = gross_w / gross_l if gross_l else float("inf")
    return "%d trades, win %.0f%%, avg %+.3fR net of fees, profit factor %.2f" % (
        len(rs), 100 * len(wins) / len(rs), statistics.mean(rs), pf)


SIM_MAX_DAYS = 60


def sim_stage(cfg, trades, start_ms, stage, max_days=None):
    max_days = max_days or SIM_MAX_DAYS
    """One stage of the challenge from start_ms. Returns (result, end_ms, n_trades)."""
    acct = cfg["account_size"]
    rules = stage_rules(cfg, stage)
    fee = cfg["firm"]["fee_pct_per_side"] / 100
    off = cfg["firm"]["daily_reset_utc_offset_hours"]
    target = rules["profit_target_pct"] / 100 * acct
    firm_daily = rules["max_daily_loss_pct"] / 100 * acct
    firm_max = rules["max_loss_pct"] / 100 * acct
    realized, today, day_pnl = 0.0, None, 0.0
    opened = closed = 0
    per_day = {}
    cap = cfg.get("schedule", {}).get("max_trades_per_day", 99)
    open_pos = []
    end_ms = start_ms + max_days * DAY_MS

    def settle(upto):
        nonlocal realized, today, day_pnl, closed
        open_pos.sort(key=lambda p: p["t_out"])
        while open_pos and open_pos[0]["t_out"] <= upto:
            p = open_pos.pop(0)
            k = day_key(p["t_out"], off)
            if k != today:
                today, day_pnl = k, 0.0
            realized += p["pnl"]
            day_pnl += p["pnl"]
            closed += 1
            if -day_pnl > firm_daily or -realized > firm_max:
                return "fail", p["t_out"]
            if realized >= target and closed >= 2 and not open_pos:
                return "pass", p["t_out"]
        return None, None

    for tr in trades:
        if tr["t_in"] < start_ms:
            continue
        if tr["t_in"] > end_ms:
            break
        res, when = settle(tr["t_in"])
        if res:
            return res, when, opened
        if realized >= target and closed >= 2:
            continue  # finish: no new trades, wait for the open ones
        if any(p["sym"] == tr["sym"] for p in open_pos):
            continue
        k = day_key(tr["t_in"], off)
        if k != today:
            today, day_pnl = k, 0.0
        if per_day.get(k, 0) >= cap:
            continue
        o_risk = sum(p["risk"] for p in open_pos)
        o_not = sum(p["notional"] for p in open_pos)
        risk, _ = risk_budget(cfg, stage, realized, day_pnl, o_risk, o_not, len(open_pos), mult=tr.get("risk_mult", 1.0))
        if risk <= 0:
            continue
        if tr["stop_frac"] * 100 < cfg["risk"]["min_stop_pct"]:
            continue
        e = 1.0
        f_t = tr.get("fee", fee)
        sz = size_trade(cfg, e, e - tr["stop_frac"], risk, o_not, f_t, tr.get("cost_side"))
        notional = sz["notional"]
        open_pos.append({"sym": tr["sym"], "t_out": tr["t_out"], "risk": sz["loss_at_stop"],
                         "notional": notional, "pnl": notional * (tr["ret"] - 2 * f_t)})
        opened += 1
        per_day[k] = per_day.get(k, 0) + 1
    res, when = settle(end_ms + 10 * DAY_MS)
    if res:
        return res, when, opened
    # Never breached a limit but never got there either. Stuck near the floor
    # (the guard stops sizing) is a fail in practice.
    floor_room = (rules["max_loss_pct"] - cfg["risk"]["max_loss_buffer_pct"]) / 100 * acct + realized
    if floor_room < cfg["risk"]["min_risk_pct"] / 100 * acct:
        return "fail", end_ms, opened
    return "timeout", end_ms, opened


def run_challenges(cfg, trades, t0, t1, every_days):
    rows = []
    s = t0
    while s < t1:
        r1, e1, n1 = sim_stage(cfg, trades, s, "1")
        row = {"start": s, "s1": r1, "d1": (e1 - s) / DAY_MS, "n1": n1, "s2": None, "d2": None}
        if r1 == "pass":
            r2, e2, n2 = sim_stage(cfg, trades, e1 + HOUR_MS, "2")
            row.update(s2=r2, d2=(e2 - e1) / DAY_MS, n2=n2)
        rows.append(row)
        s += every_days * DAY_MS
    return rows


def summarize(rows, label):
    n = len(rows)
    if not n:
        return label + ": no start dates"
    p1 = [r for r in rows if r["s1"] == "pass"]
    f1 = sum(r["s1"] == "fail" for r in rows)
    both = [r for r in p1 if r["s2"] == "pass"]
    f2 = sum(r["s2"] == "fail" for r in p1)
    med = lambda xs: statistics.median(xs) if xs else float("nan")
    def pct(xs, q):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")
    tb = [r["d1"] + r["d2"] for r in both]
    t1 = [r["d1"] for r in p1]
    dist = (" Days to pass, stage 1: median %.0f / 75%% %.0f / 90%% %.0f / longest %.0f;"
            " both stages: median %.0f / 75%% %.0f / 90%% %.0f / longest %.0f." % (
                pct(t1, .5), pct(t1, .75), pct(t1, .9), max(t1) if t1 else float("nan"),
                pct(tb, .5), pct(tb, .75), pct(tb, .9), max(tb) if tb else float("nan")))
    fast = dist + " Both stages within 7 / 10 / 14 / 30 days: %s." % " / ".join(
        "%.0f%%" % (100 * sum(r["d1"] + r["d2"] <= d for r in both) / n) for d in (7, 10, 14, 30))
    return fast[1:] + " " + ("%s: %d challenges. Stage 1 passed %.0f%% (median %.0f days, %.0f trades), failed %.0f%%, "
            "timed out %.0f%%. Both stages passed %.0f%% (median %.0f days total); stage 2 failed %.0f%% of stage-1 passes." % (
                label, n, 100 * len(p1) / n, med([r["d1"] for r in p1]), med([r["n1"] for r in p1]),
                100 * f1 / n, 100 * (n - len(p1) - f1) / n, 100 * len(both) / n,
                med([r["d1"] + r["d2"] for r in both]), 100 * f2 / len(p1) if p1 else 0))


# ---------------------------------------------------------------- commands

def cmd_rules(cfg, a):
    acct = cfg["account_size"]
    print(cfg["program"])
    for s in ("1", "2", "funded"):
        r = cfg["stages"][s]
        tgt = r["profit_target_pct"]
        print("  %-7s target %s  max daily loss %d%% (%s)  max loss %d%% (%s)" % (
            s, ("%d%% (%s realized)" % (tgt, money(tgt / 100 * acct))) if tgt else "-        ",
            r["max_daily_loss_pct"], money(r["max_daily_loss_pct"] / 100 * acct),
            r["max_loss_pct"], money(r["max_loss_pct"] / 100 * acct)))
    F, R = cfg["firm"], cfg["risk"]
    print("Firm: leverage up to %dx, fee %.2f%% of position size per side, funding: %s, day resets %s," % (
        F["max_leverage"], F["fee_pct_per_side"], F["funding"], F["daily_reset"]))
    print("  max %d open positions, total margin under %d%%, hold max %d days (majors) / %d (others),"
          " at least %d closed trades of 10+ minutes per stage, SL/TP expected, no hedging." % (
              F["max_open_positions"], F["max_margin_pct"], F["max_hold_days_major"],
              F["max_hold_days_minor"], F["min_closed_trades_per_stage"]))
    print("This tool (stricter): risk %.2f%% / %.2f%% / %.2f%% per trade (stage 1 / 2 / funded) x mult %.2f, "
          "daily guard %.1f%%, %.1f%% buffer above the max-loss floor, max %d open, open risk under %.1f%%, "
          "margin under %d%% total and %d%% per position, halve risk when down %.1f%%, finish-line sizing %s." % (
              R["stage1_risk_pct"], R["stage2_risk_pct"], R["funded_risk_pct"], R["risk_mult"], R["daily_guard_pct"],
              R["max_loss_buffer_pct"], R["max_open_positions"], R["max_open_risk_pct"], R["max_margin_pct"],
              R["max_position_margin_pct"], R["drawdown_cut_pct"], "on" if R["finish_line"] else "off"))


def time_stop_text(cfg, hours=None):
    sch = cfg["schedule"]
    now_ms = int(now_utc().timestamp() * 1000)
    hours = hours or hold_hours(cfg)
    ts, why = now_ms + hours * HOUR_MS, "%dh time stop" % hours
    if sch.get("flat_for_weekend"):
        wk = next_weekend_stop(now_ms, sch)
        if wk < ts:
            ts, why = wk, "weekend close"
    return "%s SGT (%s)" % (local_dt(ts, sch["tz_offset_hours"]).strftime("%a %d %b %H:%M"), why)


def hold_hours(cfg):
    return cfg["strategy"]["max_hold_bars"] * IV_MS[cfg["strategy"]["interval"]] // HOUR_MS


def instrument(sym):
    """Bitfunded contract size (lot) and price tick, from its instrument list."""
    m = load_markets().get(sym, {})
    dp = m.get("price_dp")
    return {"lot": m.get("lot") or 1e-8, "tick": 10 ** -dp if dp is not None else 1e-8}


def round_px(px, tick, how):
    if tick <= 0:
        return px
    n = px / tick
    n = math.floor(n + 1e-9) if how == "down" else math.ceil(n - 1e-9) if how == "up" else round(n)
    return round(n * tick, 10)


def ticket(cfg, j, sym, side, entry, stop, target=None, setup="manual", mult=1.0, mult_why="", slip=0.0, hold=None):
    st = journal_state(cfg, j)
    stage = j["stage"]
    if (side == "long" and stop >= entry) or (side == "short" and stop <= entry):
        return None, "the stop must be below the entry for a long and above it for a short"
    stop_pct = abs(entry - stop) / entry * 100
    if stop_pct < cfg["risk"]["min_stop_pct"]:
        return None, "stop %.2f%% away is under the %.2f%% minimum: fees would eat %.0f%% of the risk" % (
            stop_pct, cfg["risk"]["min_stop_pct"], 100 * 0.12 / (stop_pct + 0.12))
    sgn = 1 if side == "long" else -1
    fee_rt = 2 * cfg["firm"]["fee_pct_per_side"] / 100
    tick = instrument(sym)["tick"]
    stop = round_px(stop, tick, "down" if side == "long" else "up")       # away from the entry
    if target is None:
        # after-fee target: a hit nets target_r x (stop distance + round-trip fees), like the Trading Floor engine
        d = abs(entry - stop) + fee_rt * entry
        target = entry + sgn * (cfg["strategy"]["target_r"] * d + fee_rt * entry)
    target = round_px(target, tick, "down" if side == "long" else "up")   # toward the entry (never further away)
    entry = round_px(entry, tick, "nearest")
    if (side == "long" and target <= entry) or (side == "short" and target >= entry):
        return None, "the target must be beyond the entry"
    if any(t["symbol"] == sym for t in st["open"]):
        return None, "already holding %s: one position per coin, and hedging is banned" % sym
    tr = abs(target - entry) / abs(entry - stop)
    risk, why = risk_budget(cfg, stage, st["realized"], st["realized_today"], st["open_risk"],
                            st["open_notional"], len(st["open"]), tr, mult, mult_why)
    if risk <= 0:
        return None, "BLOCK: " + why
    costs = symbol_costs(cfg, sym)
    sz = size_trade(cfg, entry, stop, risk, st["open_notional"], costs["fee"], costs["side"] + slip,
                    load_markets().get(sym, {}).get("max_position"))
    lot = instrument(sym)["lot"]
    qty = math.floor(sz["qty"] / lot + 1e-9) * lot                         # round DOWN: risk never above budget
    if qty < lot:
        return None, "position under one Bitfunded lot (%s %s) at this risk" % (lot, sym)
    scale = qty / sz["qty"]
    for k in ("notional", "margin", "loss_at_stop", "fees_round_trip"):
        sz[k] *= scale
    sz["qty"] = qty
    major = sym in cfg["firm"]["major_assets"]
    hold_days = cfg["firm"]["max_hold_days_major"] if major else cfg["firm"]["max_hold_days_minor"]
    t = {"symbol": sym, "side": side, "setup": setup, "entry": entry, "stop": stop, "target": target,
         "qty": sz["qty"], "notional": sz["notional"], "margin": sz["margin"], "leverage": sz["leverage"],
         "risk_usd": sz["loss_at_stop"], "reward_usd": sz["notional"] * (abs(target - entry) / entry) - sz["fees_round_trip"],
         "fees_round_trip": sz["fees_round_trip"], "rr": tr, "sized_by": why if sz["limit"] == "risk" else sz["limit"],
         "stage": stage, "firm_hold_limit_days": hold_days,
         "time_stop": time_stop_text(cfg, hold)}
    return t, None


def print_ticket(cfg, t, n=None):
    acct = cfg["account_size"]
    head = ("#%d " % n) if n is not None else ""
    print("%s%s %s %s  [%s]" % (head, t["side"].upper(), t["symbol"] + "USDT perp", "", t["setup"]))
    if t.get("order"):
        print("    order: " + t["order"])
    print("    entry %s  stop %s  take-profit %s  (R:R %.1f)" % (fmt_px(t["entry"]), fmt_px(t["stop"]), fmt_px(t["target"]), t["rr"]))
    print("    qty %s %s (rounded down to Bitfunded's lot) = %s notional; isolated %dx -> margin %s (%.1f%% of account)" % (
        ("%.8f" % t["qty"]).rstrip("0").rstrip("."), t["symbol"], money(t["notional"]), t["leverage"], money(t["margin"]), 100 * t["margin"] / acct))
    print("    loss at stop %s (%.2f%% of account, fees in); gain at target %s; fees %s; sized by %s" % (
        money(t["risk_usd"]), 100 * t["risk_usd"] / acct, money(t["reward_usd"]), money(t["fees_round_trip"]), t["sized_by"]))
    print("    close by %s if neither SL nor TP has hit; firm max hold %d days" % (t["time_stop"], t["firm_hold_limit_days"]))
    print_size_menu(cfg, t)


def print_size_menu(cfg, t):
    """Reminder of what the ticket is sized for, SL/TP as price % and as % of margin at 5x, and the USDT margin /
    qty to enter at other risk levels and account sizes (capped by Bitfunded's per-coin max position)."""
    lev = cfg["firm"]["max_leverage"]; fee_rt = 2 * cfg["firm"]["fee_pct_per_side"] / 100
    e, sl, tp = t["entry"], t["stop"], t["target"]
    sl_pct = abs(e - sl) / e * 100; tp_pct = abs(tp - e) / e * 100
    acct = cfg["account_size"]
    print("    SIZED FOR: %s account, stage %s, risking %.2f%% (%s) -- set YOUR account and risk below if different" % (
        money(acct).replace(".00", ""), t["stage"], 100 * t["risk_usd"] / acct, t["sized_by"]))
    print("    SL is %.2f%% from entry = -%.1f%% of margin at %dx | TP is %.2f%% from entry = +%.1f%% of margin at %dx (before fees)" % (
        sl_pct, sl_pct * lev, lev, tp_pct, tp_pct * lev, lev))
    mp = load_markets().get(t["symbol"], {}).get("max_position")
    lot = instrument(t["symbol"])["lot"]
    sizes = sorted({acct, 50000, 100000})
    levels = [0.5, 1.0, 1.5, 1.75, 2.0, 2.5]
    print("    USDT MARGIN TO ENTER (isolated %dx), by risk %% per trade:" % lev)
    print("      %-8s " % "account" + "".join("%-11s" % ("%.2f%%" % r) for r in levels))
    for A in sizes:
        cells = []
        for r in levels:
            n = (r / 100 * A) / (sl_pct / 100 + fee_rt)
            capped = bool(mp) and n > mp
            n = min(n, mp) if mp else n
            q = math.floor(n / e / lot + 1e-9) * lot
            cells.append("%-11s" % ("$%s%s" % (format(int(q * e / lev), ","), "*" if capped else "")))
        print("      %-8s " % (format(A // 1000, "d") + "K") + "".join(cells))
    if mp:
        print("      * = capped at Bitfunded's max position for %s ($%s notional = $%s margin at %dx); that cell risks less than its column" % (
            t["symbol"], format(int(mp), ","), format(int(mp / lev), ","), lev))


def crt_setup(cfg, ind, i, btc_trend, close_ms):
    """4h candle range theory on the last two CLOSED candles (C1 = i-1, C2 = i), with the BTC trend.
    Bullish C1 (body >= body x range, range >= min_range_atr x ATR) whose high C2 sweeps and closes back
    inside -> short; mirror for a long. Returns (side, trigger, stop, target) or None. Research: 3 years,
    10 coins, +0.16R a trade, 52% win, about 4-5 a month (crt3.py htf=4h btc=1)."""
    c = cfg["strategy"].get("crt", {})
    if not c.get("enabled") or btc_trend is None or i < 2:
        return None
    o, h, l, cl, a = ind["o"], ind["h"], ind["l"], ind["c"], ind["atr"][i]
    j = i - 1
    rng = h[j] - l[j]
    if a is None or rng <= 0 or abs(cl[j] - o[j]) < c["body"] * rng or rng < c["min_range_atr"] * a:
        return None
    if cl[j] > o[j] and h[i] > h[j] and l[j] < cl[i] < h[j] and btc_trend < 0:
        side, trig, stop, tgt = "short", l[i], h[i] + c["buf_atr"] * a, l[j]
    elif cl[j] < o[j] and l[i] < l[j] and l[j] < cl[i] < h[j] and btc_trend > 0:
        side, trig, stop, tgt = "long", h[i], l[i] - c["buf_atr"] * a, h[j]
    else:
        return None
    if abs(tgt - trig) < c["min_rr"] * abs(trig - stop):
        return None
    return side, trig, stop, tgt


def swing_structure(b1, a1, minleg, look):
    """50%-retracement swing structure on 1h bars (research/ifvg2.py, unchanged logic). Yields
    (m, side, O, E, Ei, trend) when a leg O->E (>= minleg x ATR4h) is 50% retraced at 1h bar m."""
    piv = []
    d, O, Oi, E, Ei = -1, b1[0][2], 0, b1[0][3], 0
    ev = []
    for m in range(1, len(b1)):
        a = a1[m]
        if a is None:
            continue
        hi, lo = b1[m][2], b1[m][3]
        if m - Oi > look:
            w = range(max(0, m - look), Ei + 1) if Ei >= m - look else None
            if w:
                if d == -1:
                    Oi = max(w, key=lambda q: b1[q][2]); O = b1[Oi][2]
                else:
                    Oi = min(w, key=lambda q: b1[q][3]); O = b1[Oi][3]
            else:
                w = range(m - look, m + 1)
                if d == -1:
                    Oi = max(w, key=lambda q: b1[q][2]); O = b1[Oi][2]
                    Ei = min(range(Oi, m + 1), key=lambda q: b1[q][3]); E = b1[Ei][3]
                else:
                    Oi = min(w, key=lambda q: b1[q][3]); O = b1[Oi][3]
                    Ei = max(range(Oi, m + 1), key=lambda q: b1[q][2]); E = b1[Ei][2]
        if d == -1:
            if lo < E:
                E, Ei = lo, m
            elif hi >= E + 0.5 * (O - E) and O - E >= minleg * a:
                hs = [p for p, k in piv if k == 1]; ls = [p for p, k in piv if k == -1]
                if hs and hs[-1] == O:
                    hs = hs[:-1]
                ev.append((m, -1, O, E, Ei, bool(hs) and bool(ls) and O < hs[-1] and E < ls[-1]))
                piv.append((E, -1)); d, O, Oi, E, Ei = 1, E, Ei, hi, m
                continue
            if hi > O:
                if piv and piv[-1][1] == 1:
                    piv.pop()
                Oi = min(range(max(0, m - look), m + 1), key=lambda q: b1[q][3]); O = b1[Oi][3]
                d, E, Ei = 1, hi, m
        else:
            if hi > E:
                E, Ei = hi, m
            elif lo <= E - 0.5 * (E - O) and E - O >= minleg * a:
                hs = [p for p, k in piv if k == 1]; ls = [p for p, k in piv if k == -1]
                if ls and ls[-1] == O:
                    ls = ls[:-1]
                ev.append((m, 1, O, E, Ei, bool(hs) and bool(ls) and O > ls[-1] and E > hs[-1]))
                piv.append((E, 1)); d, O, Oi, E, Ei = -1, E, Ei, lo, m
                continue
            if lo < O:
                if piv and piv[-1][1] == -1:
                    piv.pop()
                Oi = max(range(max(0, m - look), m + 1), key=lambda q: b1[q][2]); O = b1[Oi][2]
                d, E, Ei = -1, lo, m
    return ev


def swing_setups(cfg, b1, b4, scan_ms, prev_ms):
    """Swing tickets due at this check-in: a big leg (>= min_leg_atr x ATR4h, with structure trend) was 50%
    retraced, then a 1h FVG formed in the retracement was inverted by a 1h close after the previous check-in
    (prev_ms) and before this one; the stop has not traded since. Returns [(side, limit, stop, info)]."""
    sw = cfg["strategy"]["swing"]
    at4 = atr([x[2] for x in b4], [x[3] for x in b4], [x[4] for x in b4], 14)
    t4 = {x[0]: k for k, x in enumerate(b4)}
    a1 = []
    for x in b1:
        k = t4.get((x[0] // (4 * HOUR_MS)) * 4 * HOUR_MS - 4 * HOUR_MS)
        a1.append(at4[k] if k is not None else None)
    out = []
    for (m0, side, O, E, Ei, tr) in swing_structure(b1, a1, sw["pivot_leg_atr"], sw["leg_lookback_h"]):
        a = a1[m0]
        if not tr or abs(O - E) < sw["min_leg_atr"] * a or b1[m0][0] < scan_ms - (sw["window_h"] + 24) * HOUR_MS:
            continue
        size = abs(O - E); inv_px = E - side * sw["invalidate"] * size
        fv = []
        for j in range(Ei + 2, m0 + 1):
            if side == -1 and b1[j][3] > b1[j - 2][2]:
                fv.append((b1[j - 2][2], b1[j][3]))
            if side == 1 and b1[j][2] < b1[j - 2][3]:
                fv.append((b1[j][2], b1[j - 2][3]))
        rx = max(x[2] for x in b1[Ei:m0 + 1]) if side == -1 else min(x[3] for x in b1[Ei:m0 + 1])
        sig = None
        for m in range(m0, min(len(b1), m0 + sw["window_h"])):
            x = b1[m]
            if m > m0:
                if side == -1 and b1[m][3] > b1[m - 2][2]:
                    fv.append((b1[m - 2][2], b1[m][3]))
                if side == 1 and b1[m][2] < b1[m - 2][3]:
                    fv.append((b1[m][2], b1[m - 2][3]))
            rx = max(rx, x[2]) if side == -1 else min(rx, x[3])
            if (side == -1 and x[4] > inv_px) or (side == 1 and x[4] < inv_px):
                break
            hit = [g for g in fv if (side == -1 and x[4] < g[0]) or (side == 1 and x[4] > g[1])]
            if hit:
                g = hit[-1]; sig = (m, (g[0] + g[1]) / 2); break
            fv = [g for g in fv if g not in hit]
        if sig is None:
            continue
        m, lim = sig
        if not (prev_ms < b1[m][0] + HOUR_MS <= scan_ms):
            continue                                   # inverted before the last check-in (already offered) or later
        stp = rx - side * sw["stop_buf_atr"] * a
        if (lim - stp) * side <= 0 or abs(lim - stp) / lim < 0.002:
            continue
        if any((side == 1 and y[3] <= stp) or (side == -1 and y[2] >= stp) for y in b1[m + 1:]):
            continue                                   # stop already traded: setup dead
        out.append((("long" if side == 1 else "short"), lim, stp,
                    {"leg": "%s -> %s (%.1f x ATR)" % (fmt_px(O), fmt_px(E), size / a), "origin_t": b1[m0][0],
                     "zone": "50%% %s / 61.8%% %s / void past 78.6%% %s" % (fmt_px(E - side * 0.5 * size), fmt_px(E - side * 0.618 * size), fmt_px(inv_px))}))
    return out


def room_r(ind, side, entry, stop, frac=3, look=540):
    """Running room: entry -> nearest untouched 4h swing in the trade direction (fractal `frac`, confirmed, last
    `look` bars, not traded through since), in R. None = clear air."""
    h, l = ind["h"], ind["l"]; n = len(h); sgn = 1 if side == "long" else -1; risk = abs(entry - stop)
    best = None
    for p in range(max(frac, n - look), n - frac):
        if sgn == 1:
            px = h[p]
            if not (px > max(h[p - frac:p]) and px > max(h[p + 1:p + 1 + frac])) or px <= entry or max(h[p + 1:]) >= px:
                continue
        else:
            px = l[p]
            if not (px < min(l[p - frac:p]) and px < min(l[p + 1:p + 1 + frac])) or px >= entry or min(l[p + 1:]) <= px:
                continue
        r = abs(px - entry) / risk
        best = r if best is None else min(best, r)
    return best


def grade_of(room):
    """Backtest 2026-11-14 (research/room.py): >=3R room +0.53R/trade, clear air +0.39, blocked <1.5R +0.41,
    1.5-3R +0.25. Used to ORDER tickets, never to skip one."""
    if room is not None and room >= 3:
        return "A+", 0
    if room is None or room < 1.5:
        return "A", 1
    return "B", 2


def cmd_scan(cfg, a):
    st = cfg["strategy"]
    sch = cfg["schedule"]
    iv = IV_MS[st["interval"]]
    syms = a.symbols.upper().split(",") if a.symbols else cfg["symbols"]
    j = load_journal()
    found, failed, watch, crt_found = [], [], [], []
    try:
        btc, feed = live_klines("BTC", st["interval"])
    except Exception:
        btc, feed = [], "none"
    if btc and is_stale(btc, st["interval"]):
        print("BTC data is stale (last closed candle %s): no tickets until the feed catches up." % (
            local_dt(btc[-1][0] + IV_MS[st["interval"]], cfg["schedule"]["tz_offset_hours"]).strftime("%a %H:%M SGT")))
        return 1
    reg = btc_regime(btc, st) if btc else {}
    close_ms = btc[-1][0] + iv if btc else 0
    off = sch["tz_offset_hours"]
    close_sgt = local_dt(close_ms, off).strftime("%a %Y-%m-%d %H:%M") if btc else "?"
    scheduled = bool(btc) and entry_allowed(close_ms, sch)
    if btc and in_weekend(close_ms, sch):
        print("Weekend pause (%s to %s SGT): no new entries. Next scans: %s" % (
            sch["weekend_stop"], sch["weekend_resume"],
            ", ".join(local_dt(t, off).strftime("%a %H:%M") for t in next_scans(sch, 3))))
        return 1
    btc_trend = reg.get(btc[-1][0]) if btc else None
    vexp = btc_vol_state(btc, cfg["risk"].get("vol_tilt", {}).get("lookback_bars", 42)).get(btc[-1][0]) if btc else None
    vm = vol_mult(cfg, vexp)
    vwhy = "BTC 7-day volatility %s" % ("expanding" if vexp else "contracting")
    st_raw = dict(st, min_body_atr=0)
    breadth = 0
    inds = {}
    for s in syms:
        try:
            bars = btc if s == "BTC" else live_klines(s, st["interval"])[0]
        except Exception:
            bars = []
        if len(bars) < st["ema_slow"] + 5 or is_stale(bars, st["interval"]) or bars[-1][0] != btc[-1][0]:
            failed.append(s)
            continue
        ind = indicators(bars, st)
        inds[s] = ind
        i = len(bars) - 1
        if signal(ind, i, st_raw):
            breadth += 1
        crt_hit = crt_setup(cfg, ind, i, btc_trend, close_ms)
        if crt_hit:
            crt_found.append((s, crt_hit))
        sig = signal(ind, i, st)
        filtered = ""
        if sig and st.get("regime_filter") and btc_trend is not None and (btc_trend > 0) != (sig["side"] == "long"):
            filtered = "%s %s skipped: against the BTC trend" % (sig["side"], s)
            sig = None
        trend = "up" if ind["ef"][i] > ind["es"][i] else "down"
        dist = (ind["c"][i] / ind["hh"][i] - 1) * 100 if trend == "up" else (ind["c"][i] / ind["ll"][i] - 1) * 100
        line = "  %-5s %-10s trend %-4s %+.2f%% from its %d-bar %s  ATR %.2f%%%s" % (
            s, fmt_px(ind["c"][i]), trend, dist, st["donchian"], "high" if trend == "up" else "low",
            100 * ind["atr"][i] / ind["c"][i], ("   [" + filtered + "]") if filtered else "")
        if sig:
            c = ind["c"][i]
            side = 1 if sig["side"] == "long" else -1
            stop = c - side * sig["stop_d"]
            if st.get("entry") == "limit":
                entry = c - side * st["limit_atr"] * ind["atr"][i]
                expiry = local_dt(close_ms + st["limit_valid_hours"] * HOUR_MS, off).strftime("%a %d %b %H:%M SGT")
            else:
                entry, expiry = c, None
            t, err = ticket(cfg, j, s, sig["side"], entry, stop, None, sig["setup"], vm, vwhy)
            if t:
                t["order"] = ("LIMIT at %s, cancel if not filled by %s" % (fmt_px(entry), expiry)) if expiry else "MARKET"
                t["room"] = room_r(ind, t["side"], t["entry"], t["stop"])
            found.append((s, sig, t, err, line))
        watch.append(line)
    print("Scan of the %s bar that closed %s SGT, %d symbols, BTC trend %s (feed: %s; confirm on BINANCE:<SYM>USDT.P)." % (
        st["interval"], close_sgt, len(syms), {1: "up: longs only", -1: "down: shorts only"}.get(btc_trend, "?"), feed))
    if vexp is not None:
        vs = load_json(path("vol_state.json"), {})
        now_state = "expanding" if vexp else "contracting"
        if vs.get("state") and vs["state"] != now_state:
            print("*** BTC VOLATILITY SWITCHED: %s -> %s (since %s). New tickets are sized %s. ***" % (
                vs["state"].upper(), now_state.upper(), vs.get("since", "?"), "UP (full risk)" if vexp else "DOWN (half risk)"))
            vs = {}
        if vs.get("state") != now_state:
            save_json(path("vol_state.json"), {"state": now_state, "since": close_sgt + " SGT"})
        print("BTC 7-day volatility: %s -> risk x%.2f (Q %.2f%%, CRT %.2f%% of the account before guards)." % (
            "EXPANDING" if vexp else "contracting", vm, cfg["risk"]["stage1_risk_pct"] * vm,
            cfg["risk"]["stage1_risk_pct"] * vm * cfg["risk"].get("setup_risk_mult", {}).get("crt4h", 1.0)))
    if not scheduled:
        print("Q: this close is not a Q close (%s SGT, skip days apply); Q tickets are withheld." % (
            ", ".join("%02d:00" % h for h in sch["scan_hours"])))
    if failed:
        print("No fresh data for (skipped): " + ", ".join(failed))
    for line in watch:
        print(line)
    sigs = []
    if not found:
        print("No setups on the last closed bar.")
    offered = load_json(path("offered.json"), {})

    def repeat(t):
        key = "%s|%s|%s|%s" % (t["symbol"], t["setup"].split()[0], t["side"], close_sgt)
        if key in offered:
            print("  (%s %s %s was already offered at %s: not re-issued)" % (t["side"], t["symbol"], t["setup"].split()[0], offered[key]))
            return True
        offered[key] = now_iso()
        return False

    maxo = min(cfg["risk"]["max_open_positions"], cfg["firm"]["max_open_positions"])
    free = max(0, maxo - len(journal_state(cfg, j)["open"]))
    cands = []                                   # (grade rank, strategy order, ticket)
    for k, (s, sig, t, err, line) in enumerate(found, 1):
        if not t:
            print("Q %s %s %s: %s" % (sig["side"], s, sig["setup"], err))
            continue
        if not scheduled:
            print("Q %s %s: skipped - Q only trades the %s SGT closes, not %s." % (sig["side"], s,
                  "/".join("%02d" % h for h in sch["scan_hours"]), "/".join(sch.get("skip_days", []))))
            continue
        t["breadth"] = breadth
        if breadth >= st.get("aplus_breadth", 99):
            t["setup"] = t["setup"] + " (%d coins breaking out together)" % breadth
        cands.append([None, 0, t])
    crt_cfg = st.get("crt", {})
    btc_daily = None
    if crt_cfg.get("enabled") and crt_cfg.get("btc_daily_filter") and crt_found:
        try:
            dbars, _ = live_klines("BTC", "1d", need=80)
            dc = [b[4] for b in dbars]
            e20, e50 = ema(dc, 20), ema(dc, 50)
            if e20[-1] is not None and e50[-1] is not None:
                btc_daily = 1 if e20[-1] > e50[-1] else -1
        except Exception:
            btc_daily = None
        if btc_daily is None:
            print("CRT: BTC daily trend unavailable, CRT tickets withheld.")
            crt_found = []
        else:
            keep = [(s_, h_) for s_, h_ in crt_found if (h_[0] == "long") == (btc_daily > 0)]
            for s_, h_ in crt_found:
                if (s_, h_) not in keep:
                    print("CRT %s %s skipped: against BTC's daily trend (EMA20 %s EMA50)." % (h_[0], s_, ">" if btc_daily > 0 else "<"))
            crt_found = keep
    if crt_cfg.get("enabled"):
        crt_hour = local_dt(close_ms, off).hour in crt_cfg["hours"]
        if WD[local_dt(close_ms, off).weekday()] in crt_cfg.get("skip_days", []):
            print("CRT: no CRT on %s (negative in both test periods)." % WD[local_dt(close_ms, off).weekday()])
            crt_hour = False
        elif not crt_hour:
            print("CRT: this close is not a CRT scan (%s SGT)." % ", ".join("%02d:00" % h for h in crt_cfg["hours"]))
        elif not crt_found:
            print("CRT: no 4h candle-range setups with the BTC trend.")
        for s, (side, trig, stop, tgt) in (crt_found if crt_hour else []):
            cm = cfg["risk"].get("setup_risk_mult", {}).get("crt4h", 1.0)
            if any(c[2]["symbol"] == s for c in cands):
                print("CRT %s %s skipped: %s already has a Q ticket this scan (one position per coin)." % (side, s, s))
                continue
            t, err = ticket(cfg, j, s, side, trig, stop, tgt, "crt4h", vm * cm, vwhy + ", CRT x%.2f" % cm,
                            crt_cfg.get("slippage_pct", 0.0) / 100, crt_cfg.get("hold_hours"))
            if err:
                print("CRT %s %s: %s" % (side, s, err))
                continue
            expiry = local_dt(close_ms + IV_MS[st["interval"]], off).strftime("%a %d %b %H:%M SGT")
            t["order"] = "%s STOP at %s (stop-limit), cancel if not triggered by %s (candle 3 close)" % (
                "SELL" if side == "short" else "BUY", fmt_px(trig), expiry)
            t["room"] = room_r(inds[s], side, t["entry"], t["stop"]) if s in inds else None
            cands.append([None, 1, t])
    sw = st.get("swing", {})
    if sw.get("enabled") and btc:
        if in_tested_weekend(close_ms, sch):
            print("SWING: off from Sat 04:00 to Sun 20:00 SGT (never tested there).")
        elif local_dt(close_ms, off).hour not in sw["hours"]:
            print("SWING: this close is not a swing check-in (%s SGT)." % ", ".join("%02d:00" % h for h in sw["hours"]))
        else:
            prev = close_ms - HOUR_MS                  # the previous check-in hour (weekend inversions lapse, as tested)
            while local_dt(prev, off).hour not in sw["hours"]:
                prev -= HOUR_MS
            uni = [k for k, v in load_markets().items() if v.get("type") == "crypto" and v.get("binance")] \
                if sw.get("symbols") == "all" else sw["symbols"]
            n_sw = 0

            def _get(sym):
                try:
                    return sym, live_klines(sym, "1h", need=800)[0], live_klines(sym, "4h", need=240)[0]
                except Exception:
                    return sym, [], []
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(8) as ex:
                got = list(ex.map(_get, uni))
            for s, b1, b4 in got:
                if len(b1) < 700 or len(b4) < 150 or is_stale(b1, "1h") or is_stale(b4, "4h"):
                    continue
                for side, lim, stp, info in swing_setups(cfg, b1, b4, close_ms, prev):
                    if any(c[2]["symbol"] == s for c in cands):
                        print("SWING %s %s skipped: %s already has a ticket this scan." % (side, s, s))
                        continue
                    t, err = ticket(cfg, j, s, side, lim, stp, None, "swing", sw["risk_mult"],
                                    "swing x%.2f" % sw["risk_mult"], 0.0, sw.get("hold_hours"))
                    if err:
                        print("SWING %s %s: %s" % (side, s, err))
                        continue
                    expiry = local_dt(close_ms + sw["valid_h"] * HOUR_MS, off).strftime("%a %d %b %H:%M SGT")
                    t["order"] = "LIMIT at %s (1h FVG midline), cancel if not filled by %s" % (fmt_px(t["entry"]), expiry)
                    t["setup"] = "swing: leg %s, %s" % (info["leg"], info["zone"])
                    t["room"] = room_r({"h": [x[2] for x in b4], "l": [x[3] for x in b4]}, side, t["entry"], t["stop"])
                    cands.append([None, 2, t]); n_sw += 1
            if not n_sw:
                print("SWING: no big-leg 50%% retracement with a 1h FVG inversion since %s SGT (%d coins checked)." % (
                    local_dt(prev, off).strftime("%a %H:%M"), len(uni)))
    for c in cands:
        g, rank = grade_of(c[2]["room"])
        c[0] = rank
        c[2]["grade"] = g
    cands.sort(key=lambda c: (c[0], c[1]))
    if len(cands) > 1:
        print("Tickets ordered best-first: grade (A+ = 3R+ of room to the next 4h swing), then Q, CRT, swing. Take them all if slots allow.")
    for c in cands:
        t = c[2]
        if repeat(t):
            continue
        if len(sigs) >= free:
            print("[%s] %s %s %s skipped: no free slot (max %d open)." % (t["grade"], t["side"], t["symbol"], t["setup"].split()[0], maxo))
            continue
        rm = "clear air (no untouched 4h swing in the way)" if t["room"] is None else "%.1fR to the next untouched 4h swing" % t["room"]
        t["setup"] = "%s | grade %s: %s" % (t["setup"], t["grade"], rm)
        print_ticket(cfg, t, len(sigs) + 1)
        sigs.append(t)
    save_json(path("offered.json"), offered)
    save_json(path("signals.json"), {"as_of": now_iso(), "bar_close_sgt": close_sgt, "scheduled": scheduled, "signals": sigs})
    ck = sch.get("checkins") or sch["scan_hours"]
    t_ = close_ms + HOUR_MS; nxt = []
    while len(nxt) < 3:
        if local_dt(t_, off).hour in ck:
            nxt.append(t_)
        t_ += HOUR_MS
    print("Next check-ins: " + ", ".join(local_dt(t, off).strftime("%a %H:%M") for t in nxt) + " SGT.")
    print("A setup is a rule match, not a prediction. Re-check the perp price before entering; signals expire at the next bar.")
    return 0 if found else 1


def cmd_plan(cfg, a):
    j = load_journal()
    t, err = ticket(cfg, j, a.symbol.upper(), a.side, a.entry, a.stop, a.target, a.setup)
    if err:
        print(err)
        return 1
    print_ticket(cfg, t)
    sig = load_json(path("signals.json"), {"signals": []})
    sig["signals"].append(t)
    sig["as_of"] = now_iso()
    save_json(path("signals.json"), sig)
    print("Saved as signal #%d. After you place it on Bitfunded: perps.py open --signal %d [--entry FILL]" % (
        len(sig["signals"]), len(sig["signals"])))
    return 0


def cmd_open(cfg, a):
    j = load_journal()
    if a.signal:
        sigs = load_json(path("signals.json"), {"signals": []})["signals"]
        if not 1 <= a.signal <= len(sigs):
            print("no signal #%d" % a.signal)
            return 1
        t = dict(sigs[a.signal - 1])
        if a.entry:
            t["entry"] = a.entry
        if a.qty:
            t["qty"] = a.qty
    else:
        if not all([a.symbol, a.side, a.entry, a.stop, a.target, a.qty]):
            print("give --signal N, or SYMBOL SIDE --entry --stop --target --qty")
            return 1
        t = {"symbol": a.symbol.upper(), "side": a.side, "setup": a.setup, "entry": a.entry,
             "stop": a.stop, "target": a.target, "qty": a.qty}
    c = symbol_costs(cfg, t["symbol"])
    t["notional"] = t["qty"] * t["entry"]
    t["risk_usd"] = t["qty"] * abs(t["entry"] - t["stop"]) + 2 * (c["fee"] + c["side"]) * t["notional"]
    st = journal_state(cfg, j)
    risk, why = risk_budget(cfg, j["stage"], st["realized"], st["realized_today"], st["open_risk"],
                            st["open_notional"], len(st["open"]))
    if t["risk_usd"] > risk * 1.05:
        print("WARNING: loss at stop %s is over the budget %s (%s). Logged anyway, since you already placed it." % (
            money(t["risk_usd"]), money(risk), why))
    t["id"] = max([x["id"] for x in j["trades"]] or [0]) + 1
    t["opened_at"] = now_iso()
    t["stage"] = j["stage"]
    j["trades"].append(t)
    save_journal(j)
    print("Opened #%d %s %s qty %.6g at %s, stop %s, target %s. Loss at stop %s." % (
        t["id"], t["side"], t["symbol"], t["qty"], fmt_px(t["entry"]), fmt_px(t["stop"]), fmt_px(t["target"]), money(t["risk_usd"])))
    return 0


def cmd_close(cfg, a):
    j = load_journal()
    for t in j["trades"]:
        if t["id"] == a.id and not t.get("closed_at"):
            side = 1 if t["side"] == "long" else -1
            gross = side * (a.exit - t["entry"]) * t["qty"]
            fees = a.fees if a.fees is not None else cfg["firm"]["fee_pct_per_side"] / 100 * t["qty"] * (t["entry"] + a.exit)
            t.update(exit=a.exit, fees=fees, pnl=gross - fees, closed_at=now_iso(),
                     r=(gross - fees) / max(1e-9, t["risk_usd"]))
            opened = parse_iso(t["opened_at"])
            if (now_utc() - opened).total_seconds() < cfg["firm"]["min_hold_minutes"] * 60:
                print("Note: held under %d minutes; Bitfunded does not count it toward the 2-trade minimum." % cfg["firm"]["min_hold_minutes"])
            save_journal(j)
            print("Closed #%d %s at %s: %s (%+.2fR), fees %s." % (t["id"], t["symbol"], fmt_px(a.exit), money(t["pnl"]), t["r"], money(fees)))
            return cmd_status(cfg, a)
    print("no open trade #%d" % a.id)
    return 1


def cmd_status(cfg, a):
    j = load_journal()
    st = journal_state(cfg, j)
    acct = cfg["account_size"]
    stage = j["stage"]
    rules = stage_rules(cfg, stage)
    R = cfg["risk"]
    stage_trades = [t for t in j["trades"] if t.get("stage") == stage]
    print("Stage %s since %s. Balance %s (realized %s)." % (stage, j["stage_started"], money(acct + st["realized"]), money(st["realized"])))
    if rules.get("profit_target_pct"):
        tgt = rules["profit_target_pct"] / 100 * acct
        print("  Target %s realized: %s to go (%.0f%% done). Closed trades: %d (need %d)." % (
            money(tgt), money(max(0, tgt - st["realized"])), 100 * max(0, st["realized"]) / tgt, st["closed"],
            cfg["firm"]["min_closed_trades_per_stage"]))
        if st["realized"] >= tgt and st["closed"] >= 2:
            print("  TARGET REACHED. Close every position; the stage advances 30 minutes after you are flat. Then: perps.py stage %s" % (
                "2" if stage == "1" else "funded"))
    fd = rules["max_daily_loss_pct"] / 100 * acct
    fm = rules["max_loss_pct"] / 100 * acct
    worst_today = -st["realized_today"] + st["open_risk"]
    worst_total = -st["realized"] + st["open_risk"]
    print("  Today (UTC+8 day): realized %s. Worst case if every stop hits: daily loss %s of the firm's %s (guard %s)." % (
        money(st["realized_today"]), money(max(0, worst_today)), money(fd), money(R["daily_guard_pct"] / 100 * acct)))
    print("  Max loss: worst case %s of the firm's %s; balance floor %s." % (money(max(0, worst_total)), money(fm), money(acct - fm)))
    print("  Open: %d positions, risk %s, notional %s, margin %.1f%% of account (firm cap %d%%)." % (
        len(st["open"]), money(st["open_risk"]), money(st["open_notional"]),
        100 * st["open_notional"] / cfg["firm"]["max_leverage"] / acct, cfg["firm"]["max_margin_pct"]))
    for t in st["open"]:
        age = (now_utc() - parse_iso(t["opened_at"])).total_seconds() / 3600
        lim = cfg["firm"]["max_hold_days_major"] if t["symbol"] in cfg["firm"]["major_assets"] else cfg["firm"]["max_hold_days_minor"]
        flag = ""
        if age > hold_hours(cfg):
            flag = "  <- past the %dh time stop: close it" % hold_hours(cfg)
        if age > (lim - 1) * 24:
            flag = "  <- CLOSE NOW: firm max hold is %d days" % lim
        print("    #%d %s %s qty %.6g in %s stop %s tp %s, open %.0fh%s" % (
            t["id"], t["side"], t["symbol"], t["qty"], fmt_px(t["entry"]), fmt_px(t["stop"]), fmt_px(t["target"]), age, flag))
    risk, why = risk_budget(cfg, stage, st["realized"], st["realized_today"], st["open_risk"], st["open_notional"], len(st["open"]))
    print("  Next trade budget: %s (%s)." % (money(risk), why))
    if stage_trades:
        rs = [t["r"] for t in stage_trades if "r" in t]
        if rs:
            print("  This stage: %d closed, win %.0f%%, avg %+.2fR." % (len(rs), 100 * sum(r > 0 for r in rs) / len(rs), statistics.mean(rs)))
    return 0


def cmd_stage(cfg, a):
    j = load_journal()
    st = journal_state(cfg, j)
    if st["open"]:
        print("Close every position first (the firm requires it to advance).")
        return 1
    j.setdefault("history", []).append({"stage": j["stage"], "started": j["stage_started"], "ended": now_iso(),
                                       "realized": st["realized"], "trades": st["closed"]})
    j["archived"] = j.get("archived", []) + j["trades"]
    j["trades"] = []
    j["stage"] = a.stage
    j["stage_started"] = now_iso()
    save_journal(j)
    print("Now in stage %s with a fresh %s balance." % (a.stage, money(cfg["account_size"])))
    return 0


def cmd_tune(cfg, a):
    """Bounded adaptation: the risk multiplier follows the last N closed trades.
    Never raises risk above max_risk_pct; never touches the firm limits or guards."""
    j = load_journal()
    closed = [t for t in j.get("archived", []) + j["trades"] if "r" in t][-a.last:]
    R = cfg["risk"]
    if len(closed) < 8:
        print("Only %d closed trades; need 8 before tuning. Multiplier stays %.2f." % (len(closed), R["risk_mult"]))
        return 0
    rs = [t["r"] for t in closed]
    exp = statistics.mean(rs)
    win = sum(r > 0 for r in rs) / len(rs)
    streak = 0
    for r in reversed(rs):
        if r > 0:
            break
        streak += 1
    if exp < -0.1 or streak >= 4:
        mult = 0.5
    elif exp < 0.05:
        mult = 0.75
    elif exp > 0.3 and len(rs) >= 15:
        mult = 1.25
    else:
        mult = 1.0
    user = load_json(path("config.json"), {})
    user.setdefault("risk", {})["risk_mult"] = mult
    save_json(path("config.json"), user)
    by_setup = {}
    for t in closed:
        by_setup.setdefault(t.get("setup", "manual"), []).append(t["r"])
    print("Last %d trades: win %.0f%%, expectancy %+.2fR, losing streak %d. Risk multiplier %.2f -> %.2f." % (
        len(rs), 100 * win, exp, streak, R["risk_mult"], mult))
    for k, v in by_setup.items():
        print("  %-9s %d trades, avg %+.2fR" % (k, len(v), statistics.mean(v)))
    print("Bounds: per-trade risk stays within %.2f%%-%.2f%%; guards and firm limits are unchanged." % (R["min_risk_pct"], R["max_risk_pct"]))
    return 0


def cmd_markets(cfg, a):
    old = load_markets()
    mk = fetch_markets()
    for name, m in mk.items():
        m["binance"] = (old.get(name) or {}).get("binance") or resolve_binance(name)
    save_json(path("markets.json"), mk)
    crypto = [k for k, v in mk.items() if v["type"] == "crypto"]
    tradfi = [k for k, v in mk.items() if v["type"] == "TradFi"]
    print("Bitfunded lists %d instruments: %d crypto, %d TradFi. Saved %s" % (len(mk), len(crypto), len(tradfi), path("markets.json")))
    print("  crypto: " + " ".join(crypto))
    print("  TradFi: " + " ".join(tradfi))
    nob = [k for k, v in mk.items() if not v["binance"]]
    if nob:
        print("  no Binance perp history: " + " ".join(nob))
    return 0


def universe(cfg, a):
    if getattr(a, "all", False):
        return [k for k, v in load_markets().items() if v.get("binance")]
    return a.symbols.upper().split(",") if getattr(a, "symbols", None) else cfg["symbols"]


def cmd_data(cfg, a):
    syms = universe(cfg, a)
    for iv in sorted({cfg["strategy"]["interval"], cfg["strategy"].get("exec_interval", "1h")}):
        for s in syms:
            bars, got = download(s, iv, a.months)
            span = ""
            if bars:
                f = lambda ms: dt.datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")
                span = "%s to %s" % (f(bars[0][0]), f(bars[-1][0]))
            print("  %-5s %s %6d bars %s (%d files fetched)" % (s, iv, len(bars), span, got))
    return 0


def cmd_backtest(cfg, a):
    st = cfg["strategy"]
    iv = st["interval"]
    if a.risk is not None:
        cfg["risk"]["stage1_risk_pct"] = a.risk
        cfg["risk"]["stage2_risk_pct"] = a.risk2 if a.risk2 is not None else a.risk * 0.75
        cfg["risk"]["max_risk_pct"] = max(cfg["risk"]["max_risk_pct"], a.risk, cfg["risk"]["stage2_risk_pct"])
        cfg["risk"]["max_open_risk_pct"] = max(cfg["risk"]["max_open_risk_pct"], 2 * a.risk)
    if a.hours:
        cfg["schedule"]["scan_hours"] = [int(x) for x in a.hours.split(",")]
    if a.max_days:
        globals()["SIM_MAX_DAYS"] = a.max_days
    if a.setups:
        st["setups"] = a.setups.split(",")
    for k in ("target_r", "atr_stop", "donchian", "max_hold_bars", "be_at_r", "entry", "limit_atr"):
        v = getattr(a, k)
        if v is not None:
            st[k] = v
    if a.holding:
        cfg["firm"]["holding_cost"] = a.holding
    if a.regime is not None:
        st["regime_filter"] = bool(a.regime)
    syms = universe(cfg, a)
    mk = load_markets()
    reg = btc_regime(load_json(cache_file("BTC", iv), []), st)
    trades = []
    t0 = t1 = None
    for s in syms:
        bars = load_json(cache_file(s, iv), [])
        if len(bars) < st["ema_slow"] + 100:
            print("  %s: not enough cached history (%d bars)" % (s, len(bars)))
            continue
        b1 = load_json(cache_file(s, st.get("exec_interval", "1h")), []) if not a.no_exec else []
        if b1:
            trades += gen_trades_exec(s, bars, b1, st, None if a.anytime else cfg["schedule"], symbol_costs(cfg, s, mk), reg)
        else:
            if not a.no_exec:
                print("  %s: no %s history, using 4h-only execution" % (s, st.get("exec_interval")))
            trades += gen_trades(s, bars, st, None if a.anytime else cfg["schedule"], symbol_costs(cfg, s, mk), reg)
        t0 = bars[0][0] if t0 is None else min(t0, bars[0][0])
        t1 = bars[-1][0] if t1 is None else max(t1, bars[-1][0])
    if not trades:
        return 1
    vstate = btc_vol_state(load_json(cache_file("BTC", iv), []), cfg["risk"].get("vol_tilt", {}).get("lookback_bars", 42))
    for t in trades:
        t["risk_mult"] = vol_mult(cfg, vstate.get(t.get("sig_t")))
    trades.sort(key=lambda t: t["t_in"])
    cut = t0 + (t1 - t0) * a.split
    ins = [t for t in trades if t["t_in"] < cut]
    oos = [t for t in trades if t["t_in"] >= cut]
    f = lambda ms: dt.datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d")
    print("Strategy %s on %s %s bars, %s to %s; fees %.2f%%/side, slippage %.2f%%/side, stop-first on ambiguous bars." % (
        "+".join(st["setups"]), ",".join(syms), iv, f(t0), f(t1), cfg["firm"]["fee_pct_per_side"], st["slippage_pct_per_side"]))
    print("  all:            " + stats(trades, cfg))
    print("  in-sample:      " + stats(ins, cfg) + "  (to %s)" % f(cut))
    print("  out-of-sample:  " + stats(oos, cfg))
    if a.detail:
        for key in ("setup", "side", "sym"):
            groups = {}
            for t in trades:
                groups.setdefault(t[key], []).append(t)
            for g, ts in sorted(groups.items()):
                print("    %-8s %-9s %s" % (key, g, stats(ts, cfg)))
    warm = t0 + 30 * DAY_MS
    rows = run_challenges(cfg, trades, warm, t1 - 60 * DAY_MS, a.every)
    R = cfg["risk"]
    print("Challenge sim, risk %.2f%% stage 1 / %.2f%% stage 2, a new start every %g days:" % (R["stage1_risk_pct"], R["stage2_risk_pct"], a.every))
    print("  " + summarize(rows, "all"))
    print("  " + summarize([r for r in rows if r["start"] >= cut], "out-of-sample starts"))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rules")
    s = sub.add_parser("scan"); s.add_argument("--symbols"); s.add_argument("-v", "--verbose", action="store_true")
    s = sub.add_parser("plan"); s.add_argument("symbol"); s.add_argument("side", choices=["long", "short"])
    s.add_argument("--entry", type=float, required=True); s.add_argument("--stop", type=float, required=True); s.add_argument("--target", type=float)
    s.add_argument("--setup", default="manual", help="tag, e.g. retrace50 (your discretionary setup) so tune reports it separately")
    s = sub.add_parser("open"); s.add_argument("symbol", nargs="?"); s.add_argument("side", nargs="?", choices=["long", "short"])
    s.add_argument("--signal", type=int); s.add_argument("--entry", type=float); s.add_argument("--stop", type=float)
    s.add_argument("--target", type=float); s.add_argument("--qty", type=float); s.add_argument("--setup", default="manual")
    s = sub.add_parser("close"); s.add_argument("id", type=int); s.add_argument("--exit", type=float, required=True); s.add_argument("--fees", type=float)
    sub.add_parser("status")
    s = sub.add_parser("stage"); s.add_argument("stage", choices=["1", "2", "funded"])
    s = sub.add_parser("tune"); s.add_argument("--last", type=int, default=20)
    sub.add_parser("markets")
    s = sub.add_parser("data"); s.add_argument("--months", type=int, default=36); s.add_argument("--symbols")
    s.add_argument("--all", action="store_true")
    s = sub.add_parser("backtest"); s.add_argument("--risk", type=float); s.add_argument("--risk2", type=float)
    s.add_argument("--every", type=float, default=2); s.add_argument("--split", type=float, default=0.67)
    s.add_argument("--symbols"); s.add_argument("--setups"); s.add_argument("--target_r", type=float)
    s.add_argument("--atr_stop", type=float); s.add_argument("--donchian", type=int); s.add_argument("--max_hold_bars", type=int)
    s.add_argument("--detail", action="store_true"); s.add_argument("--anytime", action="store_true")
    s.add_argument("--be_at_r", type=float); s.add_argument("--hours"); s.add_argument("--max_days", type=int)
    s.add_argument("--all", action="store_true"); s.add_argument("--holding", choices=["none", "settlement"])
    s.add_argument("--regime", type=int, choices=[0, 1]); s.add_argument("--no_exec", action="store_true")
    s.add_argument("--entry", choices=["market", "limit"]); s.add_argument("--limit_atr", type=float)
    a = p.parse_args(argv)
    cfg = load_config()
    return {"rules": cmd_rules, "scan": cmd_scan, "markets": cmd_markets, "plan": cmd_plan, "open": cmd_open, "close": cmd_close,
            "status": cmd_status, "stage": cmd_stage, "tune": cmd_tune, "data": cmd_data,
            "backtest": cmd_backtest}[a.cmd](cfg, a) or 0


if __name__ == "__main__":
    sys.exit(main())
