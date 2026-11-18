"""Automatic paper book for the 30-day forward test (2026-11-14 20:00 SGT -> 2026-12-14 20:00 SGT).

Run at every check-in:  PERPS_DIR=state python3 paper.py checkin
  1. pending paper orders fill or expire on real 1h candles (limit: fills when price trades to it, at the limit or a
     better open; stop-entry: triggers on touch, fills at the trigger or a worse open + 0.05% slippage; an order whose
     protective stop trades before the entry is cancelled; expired orders are cancelled);
  2. open paper trades close at stop / target / time stop (stop first if a candle touches both; no target on the fill
     candle; a gap through the stop fills at the open); P&L = qty x move - 0.04% fee per side;
  3. the normal scan runs (perps.cmd_scan) and every new ticket becomes a pending paper order.
Fills go into the bot's journal (state/journal.json) so its guards, stage and daily-loss tracking apply.
Book: state/paper.json (pending orders, event log). Experiment window in state/experiment.json."""
import sys, os, json, argparse, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perps

H = perps.HOUR_MS
SLIP = 0.0005


def iso(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sgt(ms):
    return perps.local_dt(ms, 8).strftime("%a %d %b %H:%M SGT")


def now_ms():
    return int(perps.now_utc().timestamp() * 1000)


def bars_since(sym, since_ms):
    need = max(30, int((now_ms() - since_ms) / H) + 10)
    b, _ = perps.live_klines(sym, "1h", need=min(need, 1400))
    return [x for x in b if x[0] + H > since_ms]


def load_book():
    return perps.load_json(perps.path("paper.json"), {"pending": [], "events": [], "last_run": None})


def log(book, ms, text):
    book["events"].append({"t": iso(ms), "sgt": sgt(ms), "text": text})
    print("  " + sgt(ms) + "  " + text)


def update(cfg, book, j):
    fee = cfg["firm"]["fee_pct_per_side"] / 100
    maxo = min(cfg["risk"]["max_open_positions"], cfg["firm"]["max_open_positions"])
    # 1) pending orders
    keep = []
    for o in sorted(book["pending"], key=lambda o: o["placed_ms"]):
        s = 1 if o["side"] == "long" else -1
        fill = None; dead = None
        for x in bars_since(o["symbol"], o["placed_ms"]):
            if x[0] >= o["expires_ms"]:
                dead = ("expired unfilled", o["expires_ms"]); break
            hit_stop = (s == 1 and x[3] <= o["stop"]) or (s == -1 and x[2] >= o["stop"])
            if o["kind"] == "limit":
                hit = (s == 1 and x[3] <= o["entry"]) or (s == -1 and x[2] >= o["entry"])
                px = (min(x[1], o["entry"]) if s == 1 else max(x[1], o["entry"])) if hit else None
            else:
                hit = (s == 1 and x[2] >= o["entry"]) or (s == -1 and x[3] <= o["entry"])
                px = ((max(x[1], o["entry"]) if s == 1 else min(x[1], o["entry"])) * (1 + s * SLIP)) if hit else None
            if hit_stop and not hit:
                dead = ("cancelled: stop traded before the entry", x[0]); break
            if hit:
                fill = (x[0], px); break
        if fill:
            st = perps.journal_state(cfg, j)
            if any(t["symbol"] == o["symbol"] for t in st["open"]):
                log(book, fill[0], "CANCELLED %s %s %s: already holding %s" % (o["setup"], o["side"], o["symbol"], o["symbol"]))
                continue
            if len(st["open"]) >= maxo:
                log(book, fill[0], "CANCELLED %s %s %s: no free slot (max %d open)" % (o["setup"], o["side"], o["symbol"], maxo))
                continue
            c = perps.symbol_costs(cfg, o["symbol"])
            t = {"symbol": o["symbol"], "side": o["side"], "setup": o["setup"], "entry": fill[1], "stop": o["stop"],
                 "target": o["target"], "qty": o["qty"], "paper": True, "hold_h": o["hold_h"], "fill_ms": fill[0]}
            t["notional"] = t["qty"] * t["entry"]
            t["risk_usd"] = t["qty"] * abs(t["entry"] - t["stop"]) + 2 * (c["fee"] + c["side"]) * t["notional"]
            t["id"] = max([x["id"] for x in j["trades"]] or [0]) + 1
            t["opened_at"] = iso(fill[0]); t["stage"] = j["stage"]
            j["trades"].append(t)
            log(book, fill[0], "FILLED #%d %s %s %s at %s (stop %s, target %s, risk $%.0f)" % (
                t["id"], o["setup"], o["side"], o["symbol"], perps.fmt_px(t["entry"]), perps.fmt_px(t["stop"]),
                perps.fmt_px(t["target"]), t["risk_usd"]))
        elif dead:
            log(book, dead[1], "CANCELLED %s %s %s %s at %s: %s" % (o["setup"], o["side"], o["symbol"], o["kind"],
                perps.fmt_px(o["entry"]), dead[0]))
        else:
            keep.append(o)
    book["pending"] = keep
    # 2) open trades
    for t in j["trades"]:
        if t.get("closed_at") or not t.get("paper"):
            continue
        s = 1 if t["side"] == "long" else -1
        end_ms = t["fill_ms"] + t["hold_h"] * H
        res = None
        for x in bars_since(t["symbol"], t["fill_ms"]):
            if x[0] >= end_ms:
                res = (x[1], "time stop", x[0]); break
            if (s == 1 and x[3] <= t["stop"]) or (s == -1 and x[2] >= t["stop"]):
                px = (min(x[1], t["stop"]) if s == 1 else max(x[1], t["stop"])) if x[0] > t["fill_ms"] else t["stop"]
                res = (px, "stop", x[0] + H); break
            if x[0] > t["fill_ms"] and ((s == 1 and x[2] >= t["target"]) or (s == -1 and x[3] <= t["target"])):
                res = (t["target"], "target", x[0] + H); break
        if res:
            px, why, ms = res
            gross = s * (px - t["entry"]) * t["qty"]
            fees = fee * t["qty"] * (t["entry"] + px)
            t.update(exit=px, fees=fees, pnl=gross - fees, closed_at=iso(ms), r=(gross - fees) / max(1e-9, t["risk_usd"]), exit_why=why)
            log(book, ms, "CLOSED #%d %s %s %s at %s (%s): %+.0f USD, %+.2fR" % (t["id"], t["setup"], t["side"], t["symbol"],
                perps.fmt_px(px), why, t["pnl"], t["r"]))


def add_tickets(book):
    sigs = perps.load_json(perps.path("signals.json"), {"signals": []})["signals"]
    have = {(o["symbol"], o["placed_ms"]) for o in book["pending"]}
    for t in sigs:
        if "kind" not in t or (t["symbol"], t["placed_ms"]) in have:
            continue
        o = {k: t[k] for k in ("symbol", "side", "setup", "entry", "stop", "target", "qty", "kind", "expires_ms", "hold_h", "placed_ms")}
        o["setup"] = o["setup"].split(":")[0].split()[0]
        book["pending"].append(o)
        print("  PAPER ORDER placed: %s %s %s %s at %s, stop %s, target %s, expires %s" % (
            t["setup"].split()[0].split("|")[0], t["side"], t["symbol"], t["kind"].upper(), perps.fmt_px(t["entry"]),
            perps.fmt_px(t["stop"]), perps.fmt_px(t["target"]), sgt(t["expires_ms"])))


def summary(cfg, book, j):
    acct = cfg["account_size"]
    st = perps.journal_state(cfg, j)
    flt = 0.0; lines = []
    for t in st["open"]:
        try:
            b, _ = perps.live_klines(t["symbol"], "1h", need=5)
            mk = b[-1][4]
        except Exception:
            mk = t["entry"]
        s = 1 if t["side"] == "long" else -1
        u = s * (mk - t["entry"]) * t["qty"] - cfg["firm"]["fee_pct_per_side"] / 100 * t["qty"] * (t["entry"] + mk)
        flt += u
        lines.append("    open #%d %s %s %s: entry %s, mark %s, %+.0f USD (%+.2fR), stop %s, target %s, time stop %s" % (
            t["id"], t["setup"].split()[0], t["side"], t["symbol"], perps.fmt_px(t["entry"]), perps.fmt_px(mk), u,
            u / max(1e-9, t["risk_usd"]), perps.fmt_px(t["stop"]), perps.fmt_px(t["target"]), sgt(t["fill_ms"] + t["hold_h"] * H)))
    closed = [t for t in j["trades"] if t.get("closed_at")]
    wins = sum(t["pnl"] > 0 for t in closed)
    exp = perps.load_json(perps.path("experiment.json"), {})
    print("PAPER BOOK (%s, stage %s): balance $%s realized (%+.0f), floating %+.0f -> equity $%s. Closed %d (%d won), total %+.2fR." % (
        perps.money(acct).replace(".00", ""), j["stage"], format(round(acct + st["realized"]), ","), st["realized"], flt,
        format(round(acct + st["realized"] + flt), ","), len(closed), wins, sum(t["r"] for t in closed)))
    for l in lines:
        print(l)
    for o in book["pending"]:
        print("    pending %s %s %s %s at %s, expires %s" % (o["setup"].split()[0], o["side"], o["symbol"], o["kind"],
              perps.fmt_px(o["entry"]), sgt(o["expires_ms"])))
    if exp:
        end = int(perps.parse_iso(exp["end"]).timestamp() * 1000)
        left = (end - now_ms()) / 86_400_000
        print("30-DAY EXPERIMENT: day %.0f of 30 (ends %s)%s" % (30 - left, sgt(end), "  *** EXPERIMENT ENDED ***" if left <= 0 else ""))


def replay(cfg, book, at_sgt):
    """Run a missed check-in as of `at_sgt` ("YYYY-MM-DD HH:MM", SGT): live data is cut to candles closed by then and
    the clock is set 5 minutes after the close; any tickets become paper orders placed at that time."""
    T = int(dt.datetime.strptime(at_sgt, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone(dt.timedelta(hours=8))).timestamp() * 1000)
    real_kl, real_now = perps.live_klines, perps.now_utc
    vol = perps.load_json(perps.path("vol_state.json"), None)

    def kl(sym, interval="4h", need=320):
        iv = perps.IV_MS[interval]
        extra = int((now_ms() - T) / iv) + 2
        b, src = real_kl(sym, interval, need=need + extra)
        return [x for x in b if x[0] + iv <= T], src
    perps.live_klines = kl
    perps.now_utc = lambda: dt.datetime.fromtimestamp((T + 5 * 60_000) / 1000, dt.timezone.utc)
    try:
        print("REPLAY of the missed check-in at %s:" % sgt(T))
        perps.cmd_scan(cfg, argparse.Namespace(symbols=None))
        add_tickets(book)
    finally:
        perps.live_klines, perps.now_utc = real_kl, real_now
        if vol is not None:
            perps.save_json(perps.path("vol_state.json"), vol)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["checkin", "update", "status", "replay"])
    ap.add_argument("--at", action="append", help="replay: missed check-in time(s), SGT 'YYYY-MM-DD HH:MM'")
    a = ap.parse_args()
    if a.cmd == "replay":
        cfg = perps.load_config(); book = load_book()
        for at in a.at or []:
            replay(cfg, book, at)
            print()
        perps.save_json(perps.path("paper.json"), book)
        j = perps.load_journal()
        print("Paper book update after replay:")
        n0 = len(book["events"])
        update(cfg, book, j)
        if len(book["events"]) == n0:
            print("  (no fills, cancels or closes)")
        perps.save_journal(j); perps.save_json(perps.path("paper.json"), book)
        print(); summary(cfg, book, perps.load_journal())
        return
    cfg = perps.load_config()
    book = load_book()
    if a.cmd == "checkin":
        # automatic catch-up: replay every check-in hour missed since the last scanned one (max 7 days back)
        ck = cfg["schedule"].get("checkins") or cfg["schedule"]["scan_hours"]
        cur = (now_ms() // (4 * H)) * 4 * H                      # the 4h close this check-in scans
        last = book.get("last_checkin_ms") or cur
        t = max(last, cur - 7 * 86_400_000) + H
        missed = []
        while t < cur:
            if t % (4 * H) == 0 and perps.local_dt(t, 8).hour in ck:
                missed.append(t)
            t += H
        if missed:
            print("CATCH-UP: %d missed check-in(s) replayed: %s" % (len(missed), ", ".join(sgt(m) for m in missed)))
            for m in missed:
                replay(cfg, book, perps.local_dt(m, 8).strftime("%Y-%m-%d %H:%M"))
                print()
        book["last_checkin_ms"] = cur
    j = perps.load_journal()
    if a.cmd in ("checkin", "update"):
        print("Paper book update:")
        n0 = len(book["events"])
        update(cfg, book, j)
        if len(book["events"]) == n0:
            print("  (no fills, cancels or closes since the last check-in)")
        perps.save_journal(j)
    if a.cmd == "checkin":
        print()
        perps.cmd_scan(cfg, argparse.Namespace(symbols=None))
        book = book; add_tickets(book)
    book["last_run"] = perps.now_iso()
    perps.save_json(perps.path("paper.json"), book)
    print()
    summary(cfg, book, perps.load_journal())


if __name__ == "__main__":
    main()
